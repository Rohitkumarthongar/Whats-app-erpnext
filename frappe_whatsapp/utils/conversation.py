from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import get_datetime, now_datetime

from frappe_whatsapp.utils import format_number

CUSTOMER_SERVICE_WINDOW_HOURS = 24


def pick_conversation(rows, phone):
    """Choose which existing conversation a phone number belongs to, or None.

    ``rows`` are conversation dicts (``name``, ``phone_number``, ``status``) of one
    WhatsApp account. ``phone_number`` is a unique key, so:

    * a conversation holding exactly this number always wins, whatever its status
      (a *closed* one is reopened by the caller, never duplicated);
    * otherwise a conversation with the same last 10 digits (the same contact stored
      with/without country code) is used, open ones before closed ones.
    """
    exact = [r for r in rows if r.get("phone_number") == phone]
    if exact:
        return exact[0]
    if len(phone) < 8:
        return None
    suffix = phone[-10:]
    similar = [r for r in rows if (r.get("phone_number") or "")[-10:] == suffix]
    similar.sort(key=lambda r: r.get("status") == "Closed")  # open first (sort is stable)
    return similar[0] if similar else None


def _find_conversation(phone, whatsapp_account):
    """Return the existing conversation row for ``phone`` (any status), or None.

    Different entry points hand us the same number in different shapes (a bare
    10-digit ERPNext ``mobile_no`` vs. WhatsApp's own country-code-prefixed
    ``from``/``to``), which otherwise splits one contact into several
    conversations. Matching on the last 10 digits keeps them as one thread
    without hardcoding any specific country code.

    Closed conversations are included on purpose: ``phone_number`` is unique, so
    ignoring them made the next message from that contact try to insert a second
    row and fail with "Duplicate entry ... for key 'phone_number'".
    """
    filters = {"whatsapp_account": whatsapp_account}
    if len(phone) >= 8:
        filters["phone_number"] = ["like", "%" + phone[-10:]]
    else:
        filters["phone_number"] = phone
    rows = frappe.get_all(
        "WhatsApp Conversation", filters=filters, fields=["name", "phone_number", "status"], limit_page_length=0
    )
    return pick_conversation(rows, phone)


def sync_message_to_conversation(doc, method=None):
    """after_insert hook: file the message under its conversation.

    This is bookkeeping for the inbox. If it fails it must not take the message down
    with it (the exception would roll back the whole webhook request, losing the
    reply and skipping the Approve / Reject handler that runs after this hook), so any
    error is rolled back to a savepoint and logged instead.
    """
    if doc.doctype != "WhatsApp Message":
        return
    savepoint = "whatsapp_conversation_sync"
    frappe.db.savepoint(savepoint)
    try:
        _sync_message_to_conversation(doc)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        frappe.log_error(
            title="WhatsApp conversation sync failed",
            message=f"Message {doc.get('name')} ({doc.get('type')})\n\n{frappe.get_traceback()}",
        )


def _sync_message_to_conversation(doc):
    phone = format_number(doc.get("from") if doc.type == "Incoming" else doc.to)
    if not phone or not doc.whatsapp_account:
        return
    name = None
    if doc.type == "Outgoing" and doc.template and doc.get("conversation"):
        existing = frappe.db.get_value(
            "WhatsApp Conversation",
            {"name": doc.conversation, "whatsapp_account": doc.whatsapp_account},
            "name",
        )
        if existing:
            name = existing
    if not name:
        found = _find_conversation(phone, doc.whatsapp_account)
        name = found.get("name") if found else None
    if not name:
        conv = frappe.get_doc({
            "doctype": "WhatsApp Conversation", "phone_number": phone,
            "whatsapp_account": doc.whatsapp_account,
            "customer_name": doc.profile_name or phone, "status": "Open",
            "opened_at": now_datetime(), "last_message": doc.message or doc.content_type,
            "last_message_at": doc.creation or now_datetime(),
            "last_incoming_at": doc.creation or now_datetime() if doc.type == "Incoming" else None,
            "unread_count": 1 if doc.type == "Incoming" else 0,
        }).insert(ignore_permissions=True)
    else:
        conv = frappe.get_doc("WhatsApp Conversation", name)
        # Converge on the more complete number (e.g. with country code) so the
        # stored identity stabilizes even if different senders hand us
        # different shapes of the same phone number. phone_number is unique, so never
        # move it onto a number another conversation already holds.
        if len(phone) > len(conv.phone_number or "") and not frappe.db.exists(
            "WhatsApp Conversation", {"phone_number": phone, "name": ["!=", conv.name]}
        ):
            conv.phone_number = phone
        conv.last_message = doc.message or doc.content_type
        conv.last_message_at = doc.creation or now_datetime()
        if doc.type == "Incoming":
            if conv.status == "Closed":
                # The contact wrote again: a new customer-service window starts.
                conv.status = "Open"
                conv.closed_at = None
                conv.opened_at = now_datetime()
            conv.last_incoming_at = doc.creation or now_datetime()
            conv.unread_count = (conv.unread_count or 0) + 1
            _handle_opt_out(phone, doc.message, doc.whatsapp_account)
        conv.save(ignore_permissions=True)
    if doc.get("conversation") != conv.name:
        frappe.db.set_value("WhatsApp Message", doc.name, "conversation", conv.name, update_modified=False)


def close_expired_conversations():
    """Close active chats after the WhatsApp customer-service window expires.

    WhatsApp does not allow an outbound message to reopen this window. A new
    incoming customer message creates a new active conversation automatically.
    """
    cutoff = now_datetime() - timedelta(hours=CUSTOMER_SERVICE_WINDOW_HOURS)
    conversations = frappe.get_all(
        "WhatsApp Conversation",
        filters={"status": ["in", ["Open", "Pending", "Resolved"]]},
        fields=["name", "last_incoming_at"],
        limit_page_length=0,
    )
    for conversation in conversations:
        last_incoming_at = conversation.last_incoming_at
        if not last_incoming_at:
            last_incoming_at = frappe.db.get_value(
                "WhatsApp Message",
                {"conversation": conversation.name, "type": "Incoming"},
                "creation",
                order_by="creation desc",
            )
        if last_incoming_at and get_datetime(last_incoming_at) <= cutoff:
            frappe.db.set_value(
                "WhatsApp Conversation",
                conversation.name,
                {"status": "Closed", "closed_at": now_datetime()},
                update_modified=False,
            )


def _handle_opt_out(phone, message, account):
    settings = frappe.get_single("WhatsApp Settings")
    keywords = [x.strip().upper() for x in (settings.stop_keywords or "STOP,UNSUBSCRIBE,CANCEL").split(",") if x.strip()]
    if (message or "").strip().upper() not in keywords:
        return
    filters = {"phone_number": phone, "whatsapp_account": account}
    name = frappe.db.get_value("WhatsApp Consent", filters, "name")
    values = {"status": "Opted Out", "opt_out_datetime": now_datetime(), "source": "WhatsApp"}
    if name:
        frappe.db.set_value("WhatsApp Consent", name, values)
    else:
        frappe.get_doc({"doctype": "WhatsApp Consent", **filters, **values}).insert(ignore_permissions=True)
