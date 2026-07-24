# Copyright (c) 2026, Rohit Kumar Soni and contributors
from __future__ import annotations
import json
import frappe
from frappe.model.document import Document

class WhatsAppFlowData(Document):
	def validate(self):
		if self.data:
			try: json.loads(self.data)
			except (TypeError, json.JSONDecodeError): frappe.throw("Flow data must be valid JSON")
