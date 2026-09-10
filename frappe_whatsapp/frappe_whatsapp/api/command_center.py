from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime, today

from frappe_whatsapp.utils.security import normalize_phone, require_roles

ROLES = ("System Manager", "WhatsApp Manager", "WhatsApp Agent")
MANAGER_ROLES = ("System Manager", "WhatsApp Manager")


def _settings():
    doc = frappe.get_single("WhatsApp Settings")
    return {d.fieldname: doc.get(d.fieldname) for d in frappe.get_meta("WhatsApp Settings").fields if d.fieldname}


def _conversation(name):
    doc = frappe.get_doc("WhatsApp Conversation", name)
    doc.check_permission("read")
    if "WhatsApp Agent" in frappe.get_roles() and not set(MANAGER_ROLES).intersection(frappe.get_roles()):
        if doc.assigned_to and doc.assigned_to != frappe.session.user:
            frappe.throw(_("This conversation is assigned to another agent"), frappe.PermissionError)
    return doc


@frappe.whitelist()
def get_boot_data():
    require_roles(ROLES)
    conversations = frappe.get_all("WhatsApp Conversation", fields=["name", "customer_name", "phone_number", "whatsapp_account", "status", "assigned_to", "last_message", "last_message_at", "unread_count", "sla_breached"], order_by="last_message_at desc", limit=50)
    today_start = f"{today()} 00:00:00"
    kpis = {
        "open_conversations": frappe.db.count("WhatsApp Conversation", {"status": ["in", ["Open", "Pending"]]}),
        "unread_messages": sum((x.unread_count or 0) for x in conversations),
        "messages_today": frappe.db.count("WhatsApp Message", {"creation": [">=", today_start]}),
        "sla_breached": frappe.db.count("WhatsApp Conversation", {"sla_breached": 1}),
    }
    delivery = {row.status or "Unknown": row.total for row in frappe.get_all("WhatsApp Message", fields=["status", {"COUNT": "name", "as": "total"}], group_by="status")}
    return {"kpis": kpis, "conversations": conversations, "delivery": delivery, "settings": _settings()}


@frappe.whitelist()
def get_conversation(conversation):
    require_roles(ROLES)
    conv = _conversation(conversation)
    filters = {"conversation": conv.name}
    messages = frappe.get_all("WhatsApp Message", filters=filters, fields=["name", "type", "message", "content_type", "creation", "status", "attach", "failure_reason"], order_by="creation asc", limit=500)
    if not messages:  # migration-safe fallback for older rows
        messages = frappe.get_all("WhatsApp Message", filters={"whatsapp_account": conv.whatsapp_account, "from": conv.phone_number}, fields=["name", "type", "message", "content_type", "creation", "status", "attach", "failure_reason"], order_by="creation asc", limit=250)
        messages += frappe.get_all("WhatsApp Message", filters={"whatsapp_account": conv.whatsapp_account, "to": conv.phone_number}, fields=["name", "type", "message", "content_type", "creation", "status", "attach", "failure_reason"], order_by="creation asc", limit=250)
        messages = sorted(messages, key=lambda x: str(x.creation))
    if conv.unread_count:
        frappe.db.set_value("WhatsApp Conversation", conv.name, "unread_count", 0, update_modified=False)
    return {"conversation": conv.as_dict(), "messages": messages}


@frappe.whitelist(methods=["POST"])
def send_text(conversation, message=None, attach=None, content_type="text", template=None):
    require_roles(ROLES)
    conv = _conversation(conversation)
    message = (message or "").strip()
    if not message and not attach and not template:
        frappe.throw(_("Message, attachment, or template is required"))
    phone = normalize_phone(conv.phone_number)
    settings = frappe.get_single("WhatsApp Settings")
    consent = frappe.db.get_value("WhatsApp Consent", {"phone_number": phone, "whatsapp_account": conv.whatsapp_account}, "status")
    if settings.require_opt_in and consent != "Opted In":
        frappe.throw(_("Recipient has not opted in to WhatsApp messages."))

    doc_args = {
        "doctype": "WhatsApp Message",
        "type": "Outgoing",
        "to": phone,
        "content_type": content_type,
        "message_type": "Template" if template else "Manual",
        "message": message,
        "profile_name": conv.customer_name,
        "whatsapp_account": conv.whatsapp_account,
        "conversation": conv.name
    }

    if attach:
        doc_args["attach"] = attach

    if template:
        doc_args["template"] = template

    doc = frappe.get_doc(doc_args)
    doc.insert(ignore_permissions=True)
    conv.last_message = message
    conv.last_message_at = now_datetime()
    if not conv.first_response_at and frappe.db.exists("WhatsApp Message", {"conversation": conv.name, "type": "Incoming"}):
        conv.first_response_at = now_datetime()
    conv.save(ignore_permissions=True)
    return doc.name


@frappe.whitelist(methods=["POST"])
def assign_conversation(conversation, user):
    require_roles(MANAGER_ROLES)
    conv = frappe.get_doc("WhatsApp Conversation", conversation)
    if not frappe.db.exists("User", {"name": user, "enabled": 1}):
        frappe.throw(_("Select an enabled user"))
    conv.assigned_to = user
    conv.save(ignore_permissions=True)
    return user


@frappe.whitelist(methods=["POST"])
def create_issue(conversation):
    require_roles(ROLES)
    conv = _conversation(conversation)
    settings = frappe.get_single("WhatsApp Settings")
    if not settings.enable_issue_creation:
        frappe.throw(_("Issue creation is disabled in WhatsApp Settings"))
    if conv.issue:
        return conv.issue
    issue = frappe.get_doc({"doctype": "Issue", "subject": f"WhatsApp Support - {conv.customer_name or conv.phone_number}", "description": f"Created from WhatsApp conversation {conv.name}. Phone: {conv.phone_number}", "raised_by": frappe.session.user if "@" in frappe.session.user else None, "issue_type": settings.default_issue_type or None})
    issue.insert(ignore_permissions=True)
    conv.issue = issue.name
    conv.status = "Pending"
    conv.save(ignore_permissions=True)
    return issue.name
