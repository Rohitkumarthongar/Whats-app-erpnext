from frappe import _
import frappe
from frappe.model.document import Document

class WhatsAppSettings(Document):
    def validate(self):
        for field in ("campaign_batch_size", "campaign_rate_per_minute", "sla_minutes", "message_retention_days"):
            if self.get(field) is not None and self.get(field) < 0:
                frappe.throw(_("{0} cannot be negative").format(self.meta.get_label(field)))
        if self.enable_quiet_hours and (not self.quiet_hours_start or not self.quiet_hours_end):
            frappe.throw(_("Quiet Hours Start and End are required"))
        if self.default_incoming_account and frappe.db.get_value("WhatsApp Account", self.default_incoming_account, "status") != "Active":
            frappe.throw(_("Default incoming account must be active"))
        if self.default_outgoing_account and frappe.db.get_value("WhatsApp Account", self.default_outgoing_account, "status") != "Active":
            frappe.throw(_("Default outgoing account must be active"))
        self.validate_flow_notifications()

    def validate_flow_notifications(self):
        from frappe_whatsapp.utils.flow_notifications import validate_flow_notifications

        validate_flow_notifications(self.get("flow_notifications") or [])

    def on_update(self):
        from frappe_whatsapp.utils.flow_notifications import clear_flow_notification_cache

        clear_flow_notification_cache()
