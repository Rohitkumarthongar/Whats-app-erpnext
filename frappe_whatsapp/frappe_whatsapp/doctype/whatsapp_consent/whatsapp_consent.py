from __future__ import annotations
from frappe.model.document import Document
from frappe.utils import now_datetime
from frappe_whatsapp.utils.security import normalize_phone

class WhatsAppConsent(Document):
    def validate(self):
        self.phone_number = normalize_phone(self.phone_number)
        if self.status == "Opted In" and not self.consent_datetime:
            self.consent_datetime = now_datetime()
        if self.status == "Opted Out" and not self.opt_out_datetime:
            self.opt_out_datetime = now_datetime()
