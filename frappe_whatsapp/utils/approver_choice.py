# Copyright (c) 2026, Rohit Kumar Soni and contributors
"""Send for approval to one chosen person, not to everyone who holds the approver role.

Frappe's workflow tells every user with an approver role by email, and a Flow Notification rule tells every
user with a role or designation on WhatsApp. This lets the person who sends a document for approval pick who
should approve it:

1. A pop-up on the workflow button (public/js/workflow_approver.js) asks which approver, from the same people
   the workflow would otherwise notify (get_approver_choices).
2. The pick is stored for a short while as a Workflow Approver Choice (choose_approver).
3. While the document is in the state it was sent to, the approval email (Frappe's own, narrowed in
   apply_core_patch) and the Flow Notification recipients (narrow_recipients) are limited to that person.

If no choice is stored, expired, or no longer valid, nothing changes and the usual approvers are notified, so an
approval can never end up with nobody told. Permissions are untouched: other approvers can still approve.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, get_fullname, now_datetime

DOCTYPE = "Workflow Approver Choice"
VALID_MINUTES = 15
KEEP_DAYS = 60
_ORIGINAL = {}


# --------------------------------------------------------------------------
# Who could approve
# --------------------------------------------------------------------------
def _users_the_workflow_would_notify(transitions, doc):
	"""Frappe's own list (its approval-access and read-permission rules), unaffected by any stored choice."""
	from frappe.workflow.doctype.workflow_action import workflow_action

	return (_ORIGINAL.get("get_users_next_action_data") or workflow_action.get_users_next_action_data)(transitions, doc)


def _has_whatsapp_number(user):
	from frappe_whatsapp.utils.flow_notifications import _employee_phone, normalize_phone

	return bool(normalize_phone(_employee_phone(user) or frappe.db.get_value("User", user, "mobile_no")))


def candidates(doc, action):
	"""(state the action moves the document to, [approvers]) for this action on this document."""
	from frappe.model.workflow import get_transitions, get_workflow, get_workflow_name
	from frappe.workflow.doctype.workflow_action.workflow_action import get_next_possible_transitions

	if not get_workflow_name(doc.doctype):
		return None, []
	workflow = get_workflow(doc.doctype)
	mine = [t for t in get_transitions(doc, workflow) if t.action == action]
	if not mine:
		return None, []
	next_state = mine[0].next_state
	after = get_next_possible_transitions(workflow.name, next_state, doc)
	if not after:
		return next_state, []  # nothing left to approve: a final state
	users = []
	for user, data in sorted(_users_the_workflow_would_notify(after, doc).items()):
		held = set(frappe.get_roles(user))
		users.append({
			"user": user,
			"full_name": get_fullname(user),
			"email": data.get("email"),
			"roles": sorted({t.allowed for t in after if t.allowed in held}),
			"actions": sorted({a.action_name for a in data.get("possible_actions") or []}),
			"whatsapp": _has_whatsapp_number(user),
		})
	return next_state, users


@frappe.whitelist()
def get_approver_choices(doctype, name, action):
	"""What the pop-up shows: the people who could approve once `action` is taken."""
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	next_state, users = candidates(doc, action)
	return {"required": bool(users), "next_state": next_state, "users": users, "doctype": doctype, "name": name, "action": action}


@frappe.whitelist()
def choose_approver(doctype, name, action, approver):
	"""Remember who was picked, for the state the action is about to move the document to."""
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	next_state, users = candidates(doc, action)
	picked = next((u for u in users if u["user"] == approver), None)
	if not picked:
		frappe.throw(_("{0} cannot approve this {1} at the next step. Choose someone from the list.").format(frappe.bold(get_fullname(approver) or approver), _(doctype)))
	frappe.get_doc({
		"doctype": DOCTYPE, "reference_doctype": doctype, "reference_name": name, "action": action, "workflow_state": next_state,
		"approver": approver, "chosen_by": frappe.session.user, "valid_till": add_to_date(now_datetime(), minutes=VALID_MINUTES),
	}).insert(ignore_permissions=True)
	doc.add_comment("Info", _("{0} sent this for approval to {1}.").format(frappe.bold(get_fullname(frappe.session.user)), frappe.bold(picked["full_name"])))
	return {"approver": approver, "full_name": picked["full_name"], "whatsapp": picked["whatsapp"]}


# --------------------------------------------------------------------------
# Narrowing the notifications
# --------------------------------------------------------------------------
def chosen_approver(doctype, name, state):
	"""The person picked for this document in this state, while the choice is still valid."""
	if not (doctype and name and state):
		return None
	return frappe.db.get_value(
		DOCTYPE,
		{"reference_doctype": doctype, "reference_name": name, "workflow_state": state, "valid_till": [">=", now_datetime()]},
		"approver", order_by="creation desc",
	)


def narrow_users(data, doc):
	"""Frappe's {user: email and actions} narrowed to the chosen approver; unchanged when there is none (or they are not in it)."""
	from frappe.workflow.doctype.workflow_action.workflow_action import get_doc_workflow_state

	try:
		approver = chosen_approver(doc.get("doctype"), doc.get("name"), get_doc_workflow_state(doc))
	except Exception:
		return data
	return {approver: data[approver]} if approver and approver in data else data


def _approver_roles(doc):
	from frappe.model.workflow import get_workflow_name
	from frappe.workflow.doctype.workflow_action.workflow_action import get_doc_workflow_state, get_next_possible_transitions

	name = get_workflow_name(doc.doctype)
	return {t.allowed for t in get_next_possible_transitions(name, get_doc_workflow_state(doc), doc)} if name else set()


def narrow_recipients(doc, rule, recipients):
	"""A Flow Notification's [{user, phone}] with the approvers narrowed to the chosen one. Other people on the rule
	(the document owner, a mobile field, users who are not approvers) are kept; the chosen approver is added when the rule
	addresses roles or designations and they are not already there."""
	from frappe.workflow.doctype.workflow_action.workflow_action import get_doc_workflow_state

	try:
		approver = chosen_approver(doc.doctype, doc.name, get_doc_workflow_state(doc))
		if not approver:
			return recipients
		kept = []
		for r in recipients:
			# anyone who is on the rule only because of a role or designation (not the owner or a mobile field of the document)
			# is a possible approver, whether or not the workflow itself would let them approve: only the chosen one stays
			if r.get("via") == "group" and r.get("user") != approver:
				continue
			kept.append(r)
		if not any(r.get("user") == approver for r in kept) and (rule.get("roles") or rule.get("designations")):
			from frappe_whatsapp.utils.flow_notifications import _employee_phone

			kept.append({"user": approver, "phone": _employee_phone(approver) or frappe.db.get_value("User", approver, "mobile_no")})
		return kept
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Workflow Approver Choice: could not narrow recipients")
		return recipients


def apply_core_patch():
	"""Narrow Frappe's approval email. Called when the app's hooks load, so web and worker processes both have it."""
	from frappe.workflow.doctype.workflow_action import workflow_action

	if _ORIGINAL.get("get_users_next_action_data") is not None:
		return
	original = workflow_action.get_users_next_action_data
	_ORIGINAL["get_users_next_action_data"] = original

	def get_users_next_action_data(transitions, doc):
		return narrow_users(original(transitions, doc), doc)

	workflow_action.get_users_next_action_data = get_users_next_action_data


def clear_old_choices():
	"""Daily: the table only has to remember a choice for a few minutes."""
	frappe.db.delete(DOCTYPE, {"creation": ["<", add_days(now_datetime(), -KEEP_DAYS)]})
