import frappe


def execute():
    # Backfill account-aware conversations and direct message links.
    default_in = frappe.db.get_single_value("WhatsApp Settings", "default_incoming_account")
    default_out = frappe.db.get_single_value("WhatsApp Settings", "default_outgoing_account")
    for row in frappe.get_all("WhatsApp Conversation", fields=["name", "phone_number", "whatsapp_account"]):
        if not row.whatsapp_account:
            frappe.db.set_value("WhatsApp Conversation", row.name, "whatsapp_account", default_in or default_out, update_modified=False)
    for row in frappe.get_all("WhatsApp Message", filters={"conversation": ["is", "not set"]}, fields=["name", "type", "from", "to", "whatsapp_account"], limit_page_length=0):
        phone = row["from"] if row.type == "Incoming" else row.to
        conversation = frappe.db.get_value("WhatsApp Conversation", {"phone_number": phone, "whatsapp_account": row.whatsapp_account, "status": ["!=", "Closed"]}, "name")
        if conversation:
            frappe.db.set_value("WhatsApp Message", row.name, "conversation", conversation, update_modified=False)
    try:
        frappe.db.add_unique("WhatsApp Message", ["message_id"], constraint_name="uniq_whatsapp_message_id")
    except Exception:
        # Existing duplicates must be reviewed manually; webhook code still performs idempotency checks.
        frappe.log_error("Could not add unique message_id index. Remove existing duplicate WhatsApp Message IDs and rerun migrate.", "WhatsApp v16 Migration")
    frappe.db.add_index("WhatsApp Conversation", ["whatsapp_account", "phone_number", "status"], index_name="wa_conversation_lookup")
    frappe.db.add_index("WhatsApp Message", ["conversation", "creation"], index_name="wa_message_conversation")
