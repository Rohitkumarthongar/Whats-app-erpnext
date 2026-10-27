"""Move Flow Notifications from MEL Settings (mel_platform) into WhatsApp Settings.

Runs once and only while WhatsApp Settings has no flow rows, so it is safe on sites
that never had MEL Settings and on re-runs.
"""

import frappe

OLD_PARENT = "MEL Settings"
OLD_TABLE = "tabMEL Flow Notification"
COPY = (
    "enabled", "reference_doctype", "event", "workflow_state", "condition", "whatsapp_template",
    "print_format", "send_system_notification", "send_email", "subject", "designations", "roles",
    "mobile_field", "notify_owner",
)


def execute():
    frappe.reload_doc("frappe_whatsapp", "doctype", "whatsapp_flow_notification")
    frappe.reload_doc("frappe_whatsapp", "doctype", "whatsapp_settings")
    if not frappe.db.table_exists("MEL Flow Notification"):
        return
    settings = frappe.get_single("WhatsApp Settings")
    if settings.get("flow_notifications"):
        return

    columns = set(frappe.db.get_table_columns("MEL Flow Notification"))
    rows = frappe.db.sql(
        f"select * from `{OLD_TABLE}` where parent = %s and parenttype = %s order by idx",
        (OLD_PARENT, OLD_PARENT),
        as_dict=True,
    )
    for row in rows:
        settings.append("flow_notifications", {f: row.get(f) for f in COPY if f in columns})
    for field in ("enable_flow_notifications", "apply_whatsapp_approval_replies"):
        # the fields no longer exist on MEL Settings, so read the stored value directly
        found = frappe.db.sql("select value from `tabSingles` where doctype = %s and field = %s", (OLD_PARENT, field))
        if found and found[0][0] is not None:
            settings.set(field, found[0][0])

    settings.flags.ignore_mandatory = True
    settings.flags.ignore_validate = True  # rows were validated when saved in MEL Settings
    settings.save(ignore_permissions=True)
