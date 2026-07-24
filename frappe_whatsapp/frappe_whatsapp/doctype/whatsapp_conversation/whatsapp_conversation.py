from __future__ import annotations
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from frappe_whatsapp.utils.security import normalize_phone

class WhatsAppConversation(Document):
    def validate(self):
        self.phone_number = normalize_phone(self.phone_number)
        if self.status == "Closed" and not self.closed_at:
            self.closed_at = now_datetime()
        elif self.status != "Closed":
            self.closed_at = None
        if not self.opened_at:
            self.opened_at = now_datetime()
        duplicate = frappe.db.exists("WhatsApp Conversation", {"name": ["!=", self.name], "phone_number": self.phone_number, "whatsapp_account": self.whatsapp_account, "status": ["in", ["Open", "Pending", "Resolved"]]})
        if duplicate:
            frappe.throw("An active conversation already exists for this account and phone number")
