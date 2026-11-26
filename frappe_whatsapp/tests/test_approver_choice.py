# Copyright (c) 2026, Rohit Kumar Soni and contributors
"""Send for approval to one chosen approver: who is offered, what is stored, who is told."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from frappe_whatsapp.utils import approver_choice as ac
from frappe_whatsapp.utils import flow_notifications as fn


def action(name):
	return frappe._dict(action_name=name, action_link="x")


def user_data(email, *actions):
	return frappe._dict(email=email, possible_actions=[action(a) for a in actions])


def doc(owner="maker@x.com"):
	d = frappe._dict(doctype="Quotation", name="QTN-1", owner=owner)
	d.add_comment = MagicMock()
	d.check_permission = MagicMock()
	return d


APPROVE = frappe._dict(allowed="Approver", action="Approve", next_state="Approved", state="Pending")


def workflow_patches(next_state="Pending", transitions=None, after=(APPROVE,), users=None, name="Quotation Approver"):
	"""The Frappe workflow functions candidates() leans on."""
	mine = transitions if transitions is not None else [frappe._dict(action="Submit for Approval", next_state=next_state)]
	return [
		patch("frappe.model.workflow.get_workflow_name", return_value=name),
		patch("frappe.model.workflow.get_workflow", return_value=frappe._dict(name="Quotation Approver")),
		patch("frappe.model.workflow.get_transitions", return_value=mine),
		patch("frappe.workflow.doctype.workflow_action.workflow_action.get_next_possible_transitions", return_value=list(after)),
		patch.object(ac, "_users_the_workflow_would_notify", return_value=users if users is not None else {}),
		patch.object(ac, "_has_whatsapp_number", side_effect=lambda u: u == "a@x.com"),
		patch.object(ac, "get_fullname", side_effect=lambda u: u.split("@")[0].title()),
		patch.object(ac.frappe, "get_roles", return_value=["Approver", "Desk User"]),
	]


class Patched:
	def __init__(self, patches):
		self.patches = patches

	def __enter__(self):
		for p in self.patches:
			p.start()

	def __exit__(self, *exc):
		for p in self.patches:
			p.stop()


class TestCandidates(unittest.TestCase):
	def test_lists_who_could_approve_with_roles_and_whatsapp(self):
		users = {"a@x.com": user_data("a@x.com", "Approve", "Reject"), "b@x.com": user_data("b@x.com", "Approve")}
		with Patched(workflow_patches(users=users)):
			state, found = ac.candidates(doc(), "Submit for Approval")
		self.assertEqual(state, "Pending")
		self.assertEqual([u["user"] for u in found], ["a@x.com", "b@x.com"])
		self.assertEqual(found[0], {"user": "a@x.com", "full_name": "A", "email": "a@x.com", "roles": ["Approver"], "actions": ["Approve", "Reject"], "whatsapp": True})
		self.assertFalse(found[1]["whatsapp"])

	def test_a_document_without_a_workflow_has_nobody_to_choose(self):
		with Patched(workflow_patches(name=None)):
			self.assertEqual(ac.candidates(doc(), "Submit for Approval"), (None, []))

	def test_an_action_the_user_may_not_take_offers_nothing(self):
		with Patched(workflow_patches(transitions=[])):
			self.assertEqual(ac.candidates(doc(), "Approve"), (None, []))

	def test_a_final_state_has_nobody_left_to_approve(self):
		with Patched(workflow_patches(next_state="Approved", after=())):
			state, found = ac.candidates(doc(), "Submit for Approval")
		self.assertEqual((state, found), ("Approved", []))

	def test_the_endpoint_says_whether_a_choice_is_needed(self):
		users = {"a@x.com": user_data("a@x.com", "Approve")}
		with Patched(workflow_patches(users=users)), patch.object(ac.frappe, "get_doc", return_value=doc()):
			info = ac.get_approver_choices("Quotation", "QTN-1", "Submit for Approval")
		self.assertTrue(info["required"])
		self.assertEqual((info["next_state"], len(info["users"])), ("Pending", 1))
		with Patched(workflow_patches(users={})), patch.object(ac.frappe, "get_doc", return_value=doc()):
			self.assertFalse(ac.get_approver_choices("Quotation", "QTN-1", "Submit for Approval")["required"])


class TestChooseApprover(unittest.TestCase):
	def run_choose(self, approver):
		users = {"a@x.com": user_data("a@x.com", "Approve"), "b@x.com": user_data("b@x.com", "Approve")}
		d = doc()
		inserted = []
		with Patched(workflow_patches(users=users)), patch.object(ac.frappe, "get_doc", side_effect=lambda *a, **k: d if a and a[0] == "Quotation" else MagicMock(insert=lambda **kw: inserted.append(a[0]))) as get_doc, \
			patch.object(ac.frappe, "session", frappe._dict(user="maker@x.com")), patch.object(ac, "now_datetime", return_value=__import__("datetime").datetime(2026, 11, 26, 12, 0)):
			result = ac.choose_approver("Quotation", "QTN-1", "Submit for Approval", approver)
		return result, d, get_doc

	def test_a_listed_approver_is_stored_and_noted_on_the_document(self):
		result, d, get_doc = self.run_choose("b@x.com")
		self.assertEqual((result["approver"], result["full_name"], result["whatsapp"]), ("b@x.com", "B", False))
		record = [c.args[0] for c in get_doc.call_args_list if isinstance(c.args[0], dict)][0]
		self.assertEqual((record["doctype"], record["approver"], record["workflow_state"], record["chosen_by"]), (ac.DOCTYPE, "b@x.com", "Pending", "maker@x.com"))
		self.assertEqual(str(record["valid_till"]), "2026-11-26 12:15:00")
		d.add_comment.assert_called_once()

	def test_someone_who_is_not_an_approver_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_choose("stranger@x.com")


class TestNarrowing(unittest.TestCase):
	def narrowed(self, data, approver):
		with patch.object(ac, "chosen_approver", return_value=approver), patch("frappe.workflow.doctype.workflow_action.workflow_action.get_doc_workflow_state", return_value="Pending"):
			return ac.narrow_users(data, doc())

	def test_only_the_chosen_approver_is_emailed(self):
		data = {"a@x.com": user_data("a@x.com", "Approve"), "b@x.com": user_data("b@x.com", "Approve")}
		self.assertEqual(list(self.narrowed(data, "b@x.com")), ["b@x.com"])

	def test_without_a_choice_everyone_is_emailed_as_before(self):
		data = {"a@x.com": user_data("a@x.com"), "b@x.com": user_data("b@x.com")}
		self.assertEqual(self.narrowed(data, None), data)

	def test_a_chosen_person_who_can_no_longer_approve_does_not_leave_nobody_told(self):
		data = {"a@x.com": user_data("a@x.com")}
		self.assertEqual(self.narrowed(data, "gone@x.com"), data)

	def test_a_lookup_failure_never_loses_the_email(self):
		data = {"a@x.com": user_data("a@x.com")}
		with patch.object(ac, "chosen_approver", side_effect=RuntimeError("db down")), patch("frappe.workflow.doctype.workflow_action.workflow_action.get_doc_workflow_state", return_value="Pending"):
			self.assertEqual(ac.narrow_users(data, doc()), data)

	def test_the_choice_is_looked_up_for_this_document_and_state_while_valid(self):
		with patch.object(ac.frappe.db, "get_value", return_value="b@x.com") as get_value, patch.object(ac, "now_datetime", return_value="NOW"):
			self.assertEqual(ac.chosen_approver("Quotation", "QTN-1", "Pending"), "b@x.com")
		filters = get_value.call_args.args[1]
		self.assertEqual((filters["reference_name"], filters["workflow_state"], filters["valid_till"]), ("QTN-1", "Pending", [">=", "NOW"]))
		self.assertIsNone(ac.chosen_approver("Quotation", None, "Pending"))


class TestNarrowRecipients(unittest.TestCase):
	ROLES = {"a@x.com": ["Approver"], "b@x.com": ["Approver"], "maker@x.com": ["Desk User"], "boss@x.com": ["Approver", "Director"]}

	def narrow(self, recipients, rule, approver="b@x.com"):
		d = doc()
		d.doctype = "Quotation"
		with patch.object(ac, "chosen_approver", return_value=approver), patch.object(ac, "_approver_roles", return_value={"Approver"}), \
			patch.object(ac.frappe, "get_roles", side_effect=lambda u: self.ROLES.get(u, [])), patch("frappe.workflow.doctype.workflow_action.workflow_action.get_doc_workflow_state", return_value="Pending"), \
			patch.object(fn, "_employee_phone", return_value="9000000009"), patch.object(ac.frappe.db, "get_value", return_value=None):
			return ac.narrow_recipients(d, frappe._dict(rule), recipients)

	def test_the_other_approvers_are_dropped_and_the_rest_kept(self):
		out = self.narrow(
			[{"user": "a@x.com", "phone": "1"}, {"user": "b@x.com", "phone": "2"}, {"user": "maker@x.com", "phone": "3"}, {"user": None, "phone": "4"}],
			{"roles": "Approver"},
		)
		self.assertEqual([r["user"] for r in out], ["b@x.com", "maker@x.com", None])  # owner and the mobile-field number stay

	def test_the_chosen_approver_is_added_when_the_rule_names_roles_but_they_were_missed(self):
		out = self.narrow([{"user": "a@x.com", "phone": "1"}], {"designations": "Manager"})
		self.assertEqual([r["user"] for r in out], ["b@x.com"])
		self.assertEqual(out[0]["phone"], "9000000009")

	def test_a_rule_that_names_no_roles_does_not_gain_the_approver(self):
		out = self.narrow([{"user": None, "phone": "4"}], {"mobile_field": "mobile_no"})
		self.assertEqual([r["user"] for r in out], [None])

	def test_without_a_choice_the_rule_is_untouched(self):
		rec = [{"user": "a@x.com", "phone": "1"}, {"user": "b@x.com", "phone": "2"}]
		self.assertEqual(self.narrow(rec, {"roles": "Approver"}, approver=None), rec)

	def test_a_failure_never_loses_the_message(self):
		rec = [{"user": "a@x.com", "phone": "1"}]
		with patch.object(ac, "chosen_approver", side_effect=RuntimeError("boom")), patch.object(ac.frappe, "log_error"), \
			patch("frappe.workflow.doctype.workflow_action.workflow_action.get_doc_workflow_state", return_value="Pending"):
			self.assertEqual(ac.narrow_recipients(doc(), frappe._dict(roles="Approver"), rec), rec)

	def test_flow_notifications_narrow_only_workflow_state_rules(self):
		d = frappe._dict(doctype="Quotation", name="QTN-1", owner="maker@x.com")
		for event, calls in (("Workflow State", 1), ("Submit", 0)):
			rule = frappe._dict(event=event, employee=None, designations=None, roles=None, mobile_field=None, notify_owner=1)
			with patch.object(fn, "_employee_phone", return_value="9000000001"), patch.object(ac, "narrow_recipients", side_effect=lambda doc, rule, out: out) as narrow:
				out = fn.resolve_recipients(d, rule)
			self.assertEqual(narrow.call_count, calls, event)
			self.assertEqual(out[0]["user"], "maker@x.com")


class TestCorePatch(unittest.TestCase):
	def test_frappes_email_list_is_narrowed_once_and_only_once(self):
		from frappe.workflow.doctype.workflow_action import workflow_action

		original = workflow_action.get_users_next_action_data
		saved = dict(ac._ORIGINAL)
		ac._ORIGINAL.clear()
		fake = MagicMock(return_value={"a@x.com": user_data("a@x.com"), "b@x.com": user_data("b@x.com")})
		workflow_action.get_users_next_action_data = fake
		try:
			ac.apply_core_patch()
			first = workflow_action.get_users_next_action_data
			ac.apply_core_patch()  # a second call must not wrap it again
			self.assertIs(workflow_action.get_users_next_action_data, first)
			self.assertIsNot(first, fake)
			with patch.object(ac, "chosen_approver", return_value="a@x.com"), patch.object(workflow_action, "get_doc_workflow_state", return_value="Pending"):
				self.assertEqual(list(first([], doc())), ["a@x.com"])
			with patch.object(ac, "chosen_approver", return_value=None), patch.object(workflow_action, "get_doc_workflow_state", return_value="Pending"):
				self.assertEqual(sorted(first([], doc())), ["a@x.com", "b@x.com"])
			# the pop-up lists the people Frappe would notify, not an already narrowed list
			self.assertIs(ac._ORIGINAL["get_users_next_action_data"], fake)
		finally:
			workflow_action.get_users_next_action_data = original
			ac._ORIGINAL.clear()
			ac._ORIGINAL.update(saved)
