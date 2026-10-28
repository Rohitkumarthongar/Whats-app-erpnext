# Copyright (c) 2025, Rohit Kumar Soni and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe_whatsapp.utils import format_number
from frappe_whatsapp.utils.contact_name import display_name

class WhatsAppProfiles(Document):
    def validate(self):
        self.format_whatsapp_number()
        self.set_title()

    def format_whatsapp_number(self):
        if self.number:
            self.number = format_number(self.number)

    def set_title(self):
        name = (display_name(self.number) if self.number else None) or self.profile_name
        self.title = " - ".join(p for p in (name, self.number) if p) or "Unnamed Profile"
