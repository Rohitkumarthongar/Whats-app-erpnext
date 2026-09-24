from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import get_datetime, now_datetime

from frappe_whatsapp.utils import format_number

CUSTOMER_SERVICE_WINDOW_HOURS = 24


def _find_conversation(phone, whatsapp_account):
    """Match an existing open conversation, tolerating a missing/extra country code.

    Different entry points hand us the same number in different shapes (a bare
    10-digit ERPNext ``mobile_no`` vs. WhatsApp's own country-code-prefixed
    ``from``/``to``), which otherwise splits one contact into several
    conversations. Matching on the last 10 digits keeps them as one thread
    without hardcoding any specific country code.
    """
    base_filters = {"whatsapp_account": whatsapp_account, "status": ["!=", "Closed"]}
    name = frappe.db.get_value("WhatsApp Conversation", {**base_filters, "phone_number": phone}, "name")
    if name or len(phone) < 8:
        return name
    suffix = phone[-10:]
    for row in frappe.get_all("WhatsApp Conversation", filters=base_filters, fields=["name", "phone_number"]):
        if (row.phone_number or "")[-10:] == suffix:
            return row.name
    return None


def sync_message_to_conversation(doc, method=None):
    if doc.doctype != "WhatsApp Message":
        return
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
        name = _find_conversation(phone, doc.whatsapp_account)
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
        # different shapes of the same phone number.
        if len(phone) > len(conv.phone_number or ""):
            conv.phone_number = phone
        conv.last_message = doc.message or doc.content_type
        conv.last_message_at = doc.creation or now_datetime()
        if doc.type == "Incoming":
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
