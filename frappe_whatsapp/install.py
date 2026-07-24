import frappe
ROLES=('WhatsApp Manager','WhatsApp Agent')
def after_install():
    create_roles()
    seed_settings()
def after_migrate():
    create_roles()
def create_roles():
    for role in ROLES:
        if not frappe.db.exists('Role',role): frappe.get_doc({'doctype':'Role','role_name':role,'desk_access':1}).insert(ignore_permissions=True)
def seed_settings():
    settings=frappe.get_single('WhatsApp Settings')
    settings.enable_command_center=1;settings.enable_unified_inbox=1;settings.enable_agent_assignment=1;settings.enable_crm_linking=1;settings.enable_campaigns=1;settings.enable_automation=1
    settings.save(ignore_permissions=True)
