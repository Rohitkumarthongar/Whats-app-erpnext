# Copyright (c) 2026, Rohit Kumar Soni and contributors

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_whatsapp.utils import flow_notifications as fn


def _designation(name):
	if not frappe.db.exists("Designation", name):
		frappe.get_doc({"doctype": "Designation", "designation_name": name}).insert(ignore_permissions=True)
	return name


def _user(email, mobile=None, roles=()):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"mobile_no": mobile,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
	return email


def _employee(name, designation, user=None, phone=None):
	company = frappe.db.get_value("Company", {}, "name")
	return frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": name,
			"gender": frappe.db.get_value("Gender", {}, "name"),
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
			"company": company,
			"designation": designation,
			"user_id": user,
			"cell_number": phone,
			"status": "Active",
		}
	).insert(ignore_permissions=True)


def _template(name, body, status="APPROVED"):
	if frappe.db.exists("WhatsApp Templates", name):
		frappe.delete_doc("WhatsApp Templates", name, force=1, ignore_permissions=True)
	doc = frappe.new_doc("WhatsApp Templates")
	doc.name = name
	doc.update({"template_name": name, "actual_name": name, "template": body, "language_code": "en", "status": status, "category": "UTILITY"})
	doc.flags.ignore_validate = True
	doc.db_insert()
	return doc.name


class TestFlowNotifications(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		fn.clear_flow_notification_cache()
		# user/employee saves queue cache jobs; keep tests independent of the worker
		self._queue = patch("frappe.enqueue")
		self._queue.start()

	def tearDown(self):
		self._queue.stop()
		frappe.db.rollback()
		fn.clear_flow_notification_cache()

	def test_phone_normalization(self):
		self.assertEqual(fn.normalize_phone("98765 43210"), "919876543210")
		self.assertEqual(fn.normalize_phone("+91-98765-43210"), "919876543210")
		self.assertEqual(fn.normalize_phone("09876543210"), "919876543210")
		self.assertIsNone(fn.normalize_phone(""))

	def test_recipients_from_designation_role_field_owner(self):
		des = _designation("Flow Test Accountant")
		acct = _user("flow.acct@example.com")
		_employee("Acct", des, acct, "9000000001")
		_employee("NoUser", des, None, "9000000002")
		_user("flow.role@example.com", mobile="9000000003", roles=("Accounts Manager",))
		doc = frappe._dict(owner="flow.acct@example.com", mobile_no="9000000004")
		rule = frappe._dict(designations=des, roles="Accounts Manager", mobile_field="mobile_no", notify_owner=1)
		got = fn.resolve_recipients(doc, rule)
		phones = {r["phone"] for r in got}
		users = {r["user"] for r in got if r["user"]}
		self.assertTrue({"919000000001", "919000000002", "919000000003", "919000000004"} <= phones)
		self.assertTrue({acct, "flow.role@example.com"} <= users)

	def test_chosen_employee_receives_alone(self):
		des = _designation("Flow Test Accountant")
		user = _user("flow.only@example.com")
		emp = _employee("Only", des, user, "9000000011")
		_employee("Other", des, None, "9000000012")
		doc = frappe._dict(owner="flow.only@example.com", mobile_no="9000000014")
		rule = frappe._dict(employee=emp.name, designations=des, roles="Accounts Manager", mobile_field="mobile_no", notify_owner=1)
		self.assertEqual(fn.resolve_recipients(doc, rule), [{"user": user, "phone": "919000000011"}])
		# an enabled row whose only recipient is the employee is valid
		row = frappe._dict(idx=1, reference_doctype="Sales Order", event="Submit", enabled=1, employee=emp.name)
		fn.validate_flow_notifications([row])

	def test_named_payload_uses_field_names(self):
		name = _template("flow_test_so", "Sales Order {{name}} for {{customer_name}} total {{grand_total}} by {{owner}}.")
		tpl = frappe.get_doc("WhatsApp Templates", name)
		so = frappe.get_last_doc("Sales Order")
		payload = fn.build_template_payload(so, tpl, "919000000001")
		params = payload["template"]["components"][0]["parameters"]
		self.assertEqual([p["parameter_name"] for p in params], ["name", "customer_name", "grand_total", "owner"])
		self.assertEqual(params[0]["text"], so.name)
		self.assertEqual(params[1]["text"], so.customer_name)
		self.assertTrue(all(p["text"] for p in params))

	def test_validation_rejects_unknown_variable_and_recipientless_row(self):
		_template("flow_test_bad", "Order {{name}} {{not_a_field}}")
		settings = frappe.get_single("WhatsApp Settings")
		settings.set("flow_notifications", [])
		settings.append("flow_notifications", {"reference_doctype": "Sales Order", "event": "Submit", "whatsapp_template": "flow_test_bad", "roles": "Accounts Manager"})
		with self.assertRaisesRegex(frappe.ValidationError, "not_a_field"):
			fn.validate_flow_notifications(settings.flow_notifications)
		settings.set("flow_notifications", [])
		settings.append("flow_notifications", {"reference_doctype": "Sales Order", "event": "Submit", "enabled": 0})
		fn.validate_flow_notifications(settings.flow_notifications)  # disabled rows may wait for recipients
		settings.flow_notifications[0].enabled = 1
		with self.assertRaisesRegex(frappe.ValidationError, "recipient"):
			fn.validate_flow_notifications(settings.flow_notifications)

	def test_submit_event_dispatches_only_matching_rule(self):
		des = _designation("Flow Test Accountant")
		_employee("Acct", des, None, "9000000001")
		_template("flow_test_so", "Sales Order {{name}} for {{customer_name}}.")
		settings = frappe.get_single("WhatsApp Settings")
		settings.enable_flow_notifications = 1
		settings.set("flow_notifications", [])
		settings.append("flow_notifications", {"reference_doctype": "Sales Order", "event": "Submit", "whatsapp_template": "flow_test_so", "designations": des, "send_system_notification": 0})
		settings.append("flow_notifications", {"reference_doctype": "Sales Order", "event": "Cancel", "whatsapp_template": "flow_test_so", "designations": des, "send_system_notification": 0})
		settings.save(ignore_permissions=True)
		so = frappe.get_last_doc("Sales Order")
		with patch("frappe.enqueue") as enqueue:
			fn.handle_document_event(so, "on_submit")
			fn.handle_document_event(so, "validate")
		self.assertEqual(enqueue.call_count, 1)
		kwargs = enqueue.call_args.kwargs
		self.assertEqual((kwargs["template"], kwargs["phones"]), ("flow_test_so", ["919000000001"]))
		self.assertTrue(kwargs["enqueue_after_commit"])

	def test_disabled_switch_sends_nothing(self):
		settings = frappe.get_single("WhatsApp Settings")
		settings.enable_flow_notifications = 0
		settings.set("flow_notifications", [])
		settings.append("flow_notifications", {"reference_doctype": "Sales Order", "event": "Submit", "roles": "Accounts Manager"})
		settings.save(ignore_permissions=True)
		with patch("frappe_whatsapp.utils.flow_notifications.dispatch") as dispatch:
			fn.handle_document_event(frappe.get_last_doc("Sales Order"), "on_submit")
		dispatch.assert_not_called()

	def test_send_whatsapp_logs_message_with_reference(self):
		_template("flow_test_so", "Sales Order {{name}} for {{customer_name}}.")
		so = frappe.get_last_doc("Sales Order")
		account = frappe._dict(url="https://graph.example", version="v19.0", phone_id="1", name=frappe.db.get_value("WhatsApp Account", {}, "name"), get_password=lambda f: "t")
		with patch("frappe_whatsapp.utils.get_whatsapp_account", return_value=account), patch(
			"frappe.integrations.utils.make_post_request", return_value={"messages": [{"id": "wamid.TEST1"}]}
		) as post, patch("frappe.db.commit"):
			fn.send_whatsapp("Sales Order", so.name, "flow_test_so", ["919000000001"])
		sent = json.loads(post.call_args.kwargs["data"])
		self.assertEqual(sent["template"]["components"][0]["parameters"][0]["parameter_name"], "name")
		log = frappe.db.get_value("WhatsApp Message", {"message_id": "wamid.TEST1"}, ["reference_doctype", "reference_name", "to"], as_dict=True)
		self.assertEqual((log.reference_doctype, log.reference_name, log.to), ("Sales Order", so.name, "919000000001"))

	def test_pending_template_is_not_sent(self):
		_template("flow_test_pending", "Sales Order {{name}}.", status="PENDING")
		with patch("frappe.integrations.utils.make_post_request") as post:
			fn.send_whatsapp("Sales Order", frappe.get_last_doc("Sales Order").name, "flow_test_pending", ["919000000001"])
		post.assert_not_called()

	def test_reply_from_other_number_is_ignored(self):
		frappe.get_doc({"doctype": "WhatsApp Message", "type": "Outgoing", "to": "919000000001", "message": "x", "message_id": "wamid.OUT1", "content_type": "text", "message_type": "Template", "reference_doctype": "Sales Order", "reference_name": frappe.get_last_doc("Sales Order").name}).db_insert()
		msg = frappe._dict(type="Incoming", content_type="button", reply_to_message_id="wamid.OUT1", message="Approve", message_id="wamid.IN1", whatsapp_account=None, **{"from": "919111111111"})
		with patch("frappe_whatsapp.utils.flow_notifications._reply") as reply, patch("frappe.model.workflow.apply_workflow") as apply:
			fn.apply_reply(msg)
		apply.assert_not_called()
		self.assertIn("not sent to your number", reply.call_args.args[1])

	def test_reply_applies_workflow_as_mapped_user(self):
		so = frappe.get_last_doc("Sales Order")
		approver = _user("flow.approver@example.com", roles=("Sales Manager",))
		des = _designation("Flow Test Accountant")
		_employee("Approver", des, approver, "9000000009")
		frappe.get_doc({"doctype": "WhatsApp Message", "type": "Outgoing", "to": "919000000009", "message": "x", "message_id": "wamid.OUT2", "content_type": "text", "message_type": "Template", "reference_doctype": "Sales Order", "reference_name": so.name}).db_insert()
		msg = frappe._dict(type="Incoming", content_type="button", reply_to_message_id="wamid.OUT2", message="approve", message_id="wamid.IN2", whatsapp_account=None, **{"from": "919000000009"})
		seen = {}

		def fake_apply(doc, action):
			seen["user"], seen["action"] = frappe.session.user, action

		with patch("frappe.model.workflow.get_transitions", return_value=[frappe._dict(action="Approve")]), patch(
			"frappe.model.workflow.apply_workflow", side_effect=fake_apply
		), patch("frappe_whatsapp.utils.flow_notifications._reply"), patch("frappe.db.commit"):
			fn.apply_reply(msg)
		self.assertEqual(seen, {"user": approver, "action": "Approve"})
		self.assertEqual(frappe.session.user, "Administrator")
