import unittest

import frappe


class TestRenderedTemplateText(unittest.TestCase):
	def test_conversation_shows_the_message_the_customer_received(self):
		from frappe_whatsapp.utils.flow_notifications import render_template_text

		template = frappe._dict(
			header="New Lead Received", header_type="TEXT", footer="Mahashakti Energy Limited",
			template="A new lead {{name}} has been received: {{lead_name}} ({{title}}). Lead owner: {{lead_owner}}.\nSales team: please connect as soon as possible.",
		)
		params = [("name", "CRM-LEAD-2026-00022"), ("lead_name", "ketan.shelke@bajelprojects.com"), ("title", "Bajelprojects"), ("lead_owner", "Administrator")]
		payload = {"template": {"components": [{"type": "body", "parameters": [{"type": "text", "parameter_name": k, "text": v} for k, v in params]}]}}
		self.assertEqual(
			render_template_text(template, payload),
			"New Lead Received\nA new lead CRM-LEAD-2026-00022 has been received: ketan.shelke@bajelprojects.com (Bajelprojects). "
			"Lead owner: Administrator.\nSales team: please connect as soon as possible.\nMahashakti Energy Limited",
		)

	def test_numbered_variables_and_no_header(self):
		from frappe_whatsapp.utils.flow_notifications import render_template_text

		template = frappe._dict(header=None, header_type="TEXT", footer="", template="Sheet {{1}} for {{2}}")
		payload = {"template": {"components": [{"type": "body", "parameters": [{"type": "text", "text": "TRS-1"}, {"type": "text", "text": "Acme"}]}]}}
		self.assertEqual(render_template_text(template, payload), "Sheet TRS-1 for Acme")


class TestDocumentHeader(unittest.TestCase):
	def _doc(self):
		doc = frappe._dict(doctype="Quotation", name="MEL-QTN-2026-00015", customer_name="Acme", grand_total=1000, owner="Administrator")
		doc.get_document_share_key = lambda expires_on=None, no_expiry=False: "SHAREKEY"
		doc.get = lambda key, default=None: doc[key] if key in doc else default
		doc.get_formatted = lambda field: str(doc[field])
		doc.meta = frappe._dict(has_field=lambda field: field in ("customer_name", "grand_total"))
		return doc

	def _template(self, header_type):
		return frappe._dict(
			name="quotation_approval_pdf-en", actual_name="quotation_approval_pdf", template_name="quotation_approval_pdf", language_code="en",
			header="", header_type=header_type, footer="Mahashakti Energy Limited",
			template="Quotation {{name}} for {{customer_name}}, amount {{grand_total}}, is waiting for your approval. The quotation PDF is attached.",
			get=lambda key, default=None: {"header_type": header_type, "field_names": None}.get(key, default),
		)

	def test_a_document_header_template_carries_the_pdf_before_the_body(self):
		from frappe_whatsapp.utils.flow_notifications import build_template_payload, render_template_text

		payload = build_template_payload(self._doc(), self._template("DOCUMENT"), "919800000000")
		kinds = [c["type"] for c in payload["template"]["components"]]
		self.assertEqual(kinds, ["header", "body"])
		document = payload["template"]["components"][0]["parameters"][0]["document"]
		self.assertEqual(document["filename"], "MEL-QTN-2026-00015.pdf")
		self.assertIn("/api/method/frappe.utils.print_format.download_pdf?doctype=Quotation&name=MEL-QTN-2026-00015&format=", document["link"])
		self.assertTrue(document["link"].endswith("&key=SHAREKEY"))  # opens without a login, for Meta's download
		body = payload["template"]["components"][1]["parameters"]
		self.assertEqual([p["parameter_name"] for p in body], ["name", "customer_name", "grand_total"])
		text = render_template_text(self._template("DOCUMENT"), payload)
		self.assertTrue(text.startswith("📎 MEL-QTN-2026-00015.pdf\nQuotation MEL-QTN-2026-00015 for Acme"))

	def test_a_text_template_is_unchanged(self):
		from frappe_whatsapp.utils.flow_notifications import build_template_payload

		payload = build_template_payload(self._doc(), self._template("TEXT"), "919800000000")
		self.assertEqual([c["type"] for c in payload["template"]["components"]], ["body"])

	def test_the_rows_print_format_wins_over_the_default(self):
		from frappe_whatsapp.utils.flow_notifications import print_format_for

		self.assertEqual(print_format_for("Quotation", "No Such Format"), print_format_for("Quotation"))
		any_format = frappe.db.get_value("Print Format", {"doc_type": "Quotation", "disabled": 0}, "name")
		if any_format:
			self.assertEqual(print_format_for("Quotation", any_format), any_format)
