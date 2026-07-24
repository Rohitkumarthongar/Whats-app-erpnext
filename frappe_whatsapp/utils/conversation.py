from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from frappe_whatsapp.utils import format_number


def sync_message_to_conversation(doc, method=None):
    if doc.doctype != "WhatsApp Message":
        return
    phone = format_number(doc.get("from") if doc.type == "Incoming" else doc.to)
    if not phone or not doc.whatsapp_account:
        return
    filters = {"phone_number": phone, "whatsapp_account": doc.whatsapp_account, "status": ["!=", "Closed"]}
    name = frappe.db.get_value("WhatsApp Conversation", filters, "name")
    if not name:
        conv = frappe.get_doc({
            "doctype": "WhatsApp Conversation", "phone_number": phone,
            "whatsapp_account": doc.whatsapp_account,
            "customer_name": doc.profile_name or phone, "status": "Open",
            "opened_at": now_datetime(), "last_message": doc.message or doc.content_type,
            "last_message_at": doc.creation or now_datetime(),
            "unread_count": 1 if doc.type == "Incoming" else 0,
        }).insert(ignore_permissions=True)
    else:
        conv = frappe.get_doc("WhatsApp Conversation", name)
        conv.last_message = doc.message or doc.content_type
        conv.last_message_at = doc.creation or now_datetime()
        if doc.type == "Incoming":
            conv.unread_count = (conv.unread_count or 0) + 1
            _handle_opt_out(phone, doc.message, doc.whatsapp_account)
        conv.save(ignore_permissions=True)
    if doc.get("conversation") != conv.name:
        frappe.db.set_value("WhatsApp Message", doc.name, "conversation", conv.name, update_modified=False)


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
