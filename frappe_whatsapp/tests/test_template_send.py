import json
import unittest
from unittest import mock

import frappe

from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message import whatsapp_message as module
from frappe_whatsapp.utils import template_params


def template(body, field_names=None):
	return frappe._dict(
		name="t1", template_name="t1", actual_name="t1", language_code="en", template=body, field_names=field_names,
		sample_values=None, header_type=None, buttons=[], sample=None,
	)


class Reference:
	"""A document with the fields a template can name."""

	doctype = "Quotation"
	name = "QTN-1"
	owner = "Administrator"
	modified_by = "Administrator"
	meta = mock.Mock(has_field=lambda f: f in ("customer_name", "grand_total"))

	def get(self, field):
		return {"customer_name": "ABC Ltd", "grand_total": 1500, "name": "QTN-1"}.get(field)

	def get_formatted(self, field):
		return {"customer_name": "ABC Ltd", "grand_total": "₹ 1,500.00"}[field]


def send(tpl, ref=None, **fields):
	message = frappe.new_doc("WhatsApp Message")
	message.update({"to": "+91 98789 06000", "template": "t1", "message_type": "Template", **fields})
	if ref:
		message.reference_doctype, message.reference_name = ref.doctype, ref.name
	captured = {}

	def get_doc(doctype, name=None, *args, **kwargs):
		if doctype == "WhatsApp Templates":
			return tpl
		return ref

	with mock.patch.object(module.frappe, "get_doc", side_effect=get_doc), \
		mock.patch.object(module.frappe.db, "exists", return_value=True), \
		mock.patch.object(type(message), "notify", lambda self, data: captured.update(data)):
		message.send_template()
	return captured


class TestTemplateSend(unittest.TestCase):
	def test_named_variables_are_filled_from_the_document_with_their_names(self):
		data = send(template("Quotation {{name}} for {{customer_name}}: {{grand_total}}"), Reference())
		body = next(c for c in data["template"]["components"] if c["type"] == "body")
		self.assertEqual(
			body["parameters"],
			[
				{"type": "text", "parameter_name": "name", "text": "QTN-1"},
				{"type": "text", "parameter_name": "customer_name", "text": "ABC Ltd"},
				{"type": "text", "parameter_name": "grand_total", "text": "₹ 1,500.00"},
			],
		)

	def test_unresolvable_variable_says_which_one_and_what_to_do(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			send(template("Hi {{customer_name}}, due {{due_date}}"), Reference())
		text = str(caught.exception)
		self.assertIn("due_date", text)
		self.assertIn("Quotation", text)

	def test_numbered_variables_without_fields_are_explained_before_meta_is_called(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			send(template("Hi {{1}} and {{2}}"), Reference())
		self.assertIn("Field Names", str(caught.exception))

	def test_numbered_variables_with_fields_still_work(self):
		tpl = template("Hi {{1}} total {{2}}", field_names="customer_name,grand_total")
		tpl.sample_values = "a,b"
		data = send(tpl, Reference())
		body = next(c for c in data["template"]["components"] if c["type"] == "body")
		self.assertEqual([p["text"] for p in body["parameters"]], ["ABC Ltd", "₹ 1,500.00"])
		self.assertTrue(all("parameter_name" not in p for p in body["parameters"]))

	def test_explicit_body_param_is_left_alone(self):
		tpl = template("Hi {{customer_name}}")
		tpl.sample_values = "x"
		tpl.field_names = "customer_name"
		data = send(tpl, None, body_param=json.dumps({"1": "Given"}))
		body = next(c for c in data["template"]["components"] if c["type"] == "body")
		self.assertEqual(body["parameters"], [{"type": "text", "text": "Given"}])

	def test_person_variable_without_a_document_comes_from_the_number(self):
		with mock.patch.object(template_params, "display_name", return_value="Karan Singh"):
			params, values = template_params.named_parameters(["customer_name"], None, "919878906000", "t1")
		self.assertEqual(values, ["Karan Singh"])
		self.assertEqual(params[0]["parameter_name"], "customer_name")


class TestFriendlyError(unittest.TestCase):
	def test_parameter_mismatch_names_expected_and_sent(self):
		data = {"template": {"components": [{"type": "body", "parameters": []}]}}
		res = {"code": 132000, "message": "(#132000) Number of parameters does not match the expected number of params", "error_data": {"details": "body: number of localizable_params (0) does not match the expected number of params (4)"}}
		with mock.patch.object(template_params.frappe.db, "exists", return_value=True), \
			mock.patch.object(template_params.frappe, "get_doc", return_value=template("{{name}} {{customer_name}} {{grand_total}} {{owner}}")):
			text, details = template_params.friendly_error(res, data, "t1")
		self.assertIn("expects 4", text)
		self.assertIn("0 were sent", text)
		self.assertIn("localizable_params", details)

	def test_other_codes_get_plain_wording(self):
		text, _details = template_params.friendly_error({"code": 131030, "message": "x"}, {}, None)
		self.assertIn("allowed list", text)
