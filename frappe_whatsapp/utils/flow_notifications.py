# Copyright (c) 2026, Rohit Kumar Soni and contributors
"""Flow notifications configured in WhatsApp Settings → Flow Notifications.

Each row says: when <Document> reaches <event>, send <WhatsApp template> and/or a
system notification / email to the listed designations, roles and document
mobile field. Template variables are named after document fields
({{customer_name}}), so the value is read from the field with the same name.

Quick-reply buttons on a workflow template (e.g. Approve / Reject) are applied
back to the document as the approver's user, so the workflow's own role rules
decide whether the action is allowed.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, get_fullname

CACHE_KEY = "whatsapp_flow_notification_rules"
EVENTS = {
	"after_insert": "New",
	"on_submit": "Submit",
	"on_cancel": "Cancel",
	"on_update": "Workflow State",
	"on_update_after_submit": "Workflow State",
}
SKIP_DOCTYPES = {"WhatsApp Settings", "WhatsApp Message", "WhatsApp Notification Log", "Notification Log", "Version", "Comment", "Error Log"}
VARIABLE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*|\d+)\s*}}")


def _lines(value):
	return [v.strip() for v in (value or "").replace(",", "\n").split("\n") if v.strip()]


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
def validate_flow_notifications(rows):
	for row in rows:
		label = _("Flow Notification row {0}").format(row.idx)
		if row.event == "Workflow State" and not row.workflow_state:
			frappe.throw(_("{0}: set the Workflow State to notify on.").format(label))
		for designation in _lines(row.designations):
			if not frappe.db.exists("Designation", designation):
				frappe.throw(_("{0}: Designation {1} does not exist.").format(label, frappe.bold(designation)))
		for role in _lines(row.roles):
			if not frappe.db.exists("Role", role):
				frappe.throw(_("{0}: Role {1} does not exist.").format(label, frappe.bold(role)))
		meta = frappe.get_meta(row.reference_doctype)
		if row.mobile_field and not meta.has_field(row.mobile_field):
			frappe.throw(_("{0}: {1} has no field {2}.").format(label, row.reference_doctype, frappe.bold(row.mobile_field)))
		if row.whatsapp_template:
			if not frappe.db.exists("DocType", "WhatsApp Templates") or not frappe.db.exists("WhatsApp Templates", row.whatsapp_template):
				frappe.throw(_("{0}: WhatsApp Template {1} not found. Fetch templates from Meta first.").format(label, frappe.bold(row.whatsapp_template)))
			body = frappe.db.get_value("WhatsApp Templates", row.whatsapp_template, "template") or ""
			missing = [v for v in _template_variables(body) if not v.isdigit() and v != "name" and not meta.has_field(v) and v not in ("owner", "modified_by", "creation", "modified")]
			if missing:
				frappe.throw(_("{0}: template variables {1} are not fields of {2}.").format(label, ", ".join(missing), row.reference_doctype))
		if cint(row.enabled) and not (row.employee or row.designations or row.roles or row.mobile_field or row.notify_owner):
			frappe.throw(_("{0}: add at least one recipient (employee, designation, role, mobile field or owner).").format(label))


def clear_flow_notification_cache():
	frappe.cache.delete_value(CACHE_KEY)


def _rules():
	rules = frappe.cache.get_value(CACHE_KEY)
	if rules is None:
		rules = {}
		try:
			settings = frappe.get_cached_doc("WhatsApp Settings")
			if cint(settings.get("enable_flow_notifications")):
				for row in settings.get("flow_notifications") or []:
					if cint(row.enabled):
						rules.setdefault(row.reference_doctype, []).append(row.as_dict())
		except Exception:
			rules = {}
		frappe.cache.set_value(CACHE_KEY, rules)
	return rules


# --------------------------------------------------------------------------
# Document events
# --------------------------------------------------------------------------
def handle_document_event(doc, method=None):
	"""Global hook; exits immediately for DocTypes without a configured rule."""
	event = EVENTS.get(method)
	if not event or doc.doctype in SKIP_DOCTYPES:
		return
	rules = _rules().get(doc.doctype)
	if not rules:
		return
	for rule in rules:
		if rule["event"] != event:
			continue
		if event == "Workflow State" and not _entered_state(doc, rule["workflow_state"]):
			continue
		try:
			if rule.get("condition") and not frappe.safe_eval(rule["condition"], None, {"doc": doc.as_dict()}):
				continue
			dispatch(doc, frappe._dict(rule))
		except Exception:
			# a notification must never block the user's save/submit
			frappe.log_error(frappe.get_traceback(), f"WhatsApp Flow Notification: {doc.doctype} {doc.name}")


def _entered_state(doc, state):
	from frappe.model.workflow import get_workflow_name

	if not get_workflow_name(doc.doctype):
		return False
	field = _state_field(doc.doctype)
	before = doc.get_doc_before_save()
	return doc.get(field) == state and (not before or before.get(field) != state)


def dispatch(doc, rule):
	recipients = resolve_recipients(doc, rule)
	if rule.whatsapp_template:
		phones = sorted({r["phone"] for r in recipients if r.get("phone")})
		if phones:
			frappe.enqueue(
				"frappe_whatsapp.utils.flow_notifications.send_whatsapp",
				queue="short",
				enqueue_after_commit=True,
				doctype=doc.doctype,
				name=doc.name,
				template=rule.whatsapp_template,
				phones=phones,
				print_format=rule.get("print_format"),
			)
	users = sorted({r["user"] for r in recipients if r.get("user")})
	if users and (cint(rule.send_system_notification) or cint(rule.send_email)):
		subject = _subject(doc, rule)
		if cint(rule.send_system_notification):
			from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

			enqueue_create_notification(
				users,
				{"type": "Alert", "document_type": doc.doctype, "document_name": doc.name, "subject": subject, "from_user": frappe.session.user},
			)
		if cint(rule.send_email):
			emails = [e for e in frappe.get_all("User", filters={"name": ["in", users], "enabled": 1}, pluck="email") if e]
			if emails:
				frappe.sendmail(
					recipients=emails,
					subject=subject,
					message=_("{0} {1}: {2}").format(_(doc.doctype), doc.name, subject)
					+ f'<br><a href="{frappe.utils.get_url_to_form(doc.doctype, doc.name)}">{_("Open")}</a>',
					reference_doctype=doc.doctype,
					reference_name=doc.name,
					now=False,
				)


def _subject(doc, rule):
	if rule.subject:
		return frappe.render_template(rule.subject, {"doc": doc})
	event = rule.workflow_state if rule.event == "Workflow State" else {"New": _("created"), "Submit": _("submitted"), "Cancel": _("cancelled")}[rule.event]
	return f"{_(doc.doctype)} {doc.name} {event}"


def resolve_recipients(doc, rule):
	"""[{user, phone}] from the chosen employee alone, else designations, roles, document mobile field and owner."""
	if rule.get("employee"):
		user, phone = frappe.db.get_value("Employee", rule.employee, ["user_id", "cell_number"]) or (None, None)
		return [{"user": user, "phone": normalize_phone(phone)}]
	out = []
	designations = _lines(rule.designations)
	if designations:
		for emp in frappe.get_all(
			"Employee",
			filters={"status": "Active", "designation": ["in", designations]},
			fields=["user_id", "cell_number"],
		):
			out.append({"user": emp.user_id, "phone": emp.cell_number})
	roles = _lines(rule.roles)
	if roles:
		users = set(
			frappe.get_all("Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent")
		)
		for user in frappe.get_all(
			"User",
			filters={"name": ["in", list(users) or [""]], "enabled": 1, "user_type": "System User"},
			fields=["name", "mobile_no"],
		):
			if user.name in ("Administrator", "Guest"):
				continue
			out.append({"user": user.name, "phone": _employee_phone(user.name) or user.mobile_no})
	if rule.mobile_field and doc.get(rule.mobile_field):
		out.append({"user": None, "phone": doc.get(rule.mobile_field)})
	if cint(rule.notify_owner) and doc.owner not in ("Administrator", "Guest"):
		out.append({"user": doc.owner, "phone": _employee_phone(doc.owner) or frappe.db.get_value("User", doc.owner, "mobile_no")})
	for r in out:
		r["phone"] = normalize_phone(r.get("phone"))
	return out


def _employee_phone(user):
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "cell_number")


def normalize_phone(phone, default_country_code="91"):
	digits = re.sub(r"\D", "", phone or "")
	if not digits:
		return None
	if len(digits) == 10:
		digits = default_country_code + digits
	elif len(digits) == 11 and digits.startswith("0"):
		digits = default_country_code + digits[1:]
	return digits


# --------------------------------------------------------------------------
# WhatsApp
# --------------------------------------------------------------------------
def _template_variables(body):
	seen = []
	for name in VARIABLE.findall(body or ""):
		if name not in seen:
			seen.append(name)
	return seen


def template_value(doc, field):
	if field in ("owner", "modified_by"):
		value = get_fullname(doc.get(field))
	elif field == "name":
		value = doc.name
	else:
		value = doc.get_formatted(field) if doc.meta.has_field(field) else doc.get(field)
	value = frappe.utils.strip_html(str(value)) if value not in (None, "") else ""
	# Meta rejects empty parameters and newlines inside a parameter
	return re.sub(r"\s+", " ", value).strip() or "-"


def print_format_for(doctype, chosen=None):
	"""The print format a document is attached in: the row's choice, else the document type's default."""
	if chosen and frappe.db.exists("Print Format", chosen):
		return chosen
	default = frappe.db.get_value("Property Setter", {"doc_type": doctype, "property": "default_print_format"}, "value")
	return default or frappe.get_meta(doctype).default_print_format or "Standard"


def document_header(doc, print_format=None):
	"""Header component carrying the document as a PDF. Meta downloads it from a time-limited
	link, so the link carries a Document Share Key and needs no login."""
	from frappe.desk.form.utils import get_pdf_link

	key = doc.get_document_share_key(expires_on=frappe.utils.add_days(frappe.utils.nowdate(), 1))
	link = get_pdf_link(doc.doctype, doc.name, print_format=print_format_for(doc.doctype, print_format))
	filename = f"{doc.name}.pdf"
	return {"type": "header", "parameters": [{"type": "document", "document": {"link": f"{frappe.utils.get_url()}{link}&key={key}", "filename": filename}}]}, filename


def build_template_payload(doc, template, phone, print_format=None):
	"""Meta Cloud API payload; named variables carry their parameter_name. A template with a
	Document header carries the document as a PDF."""
	variables = _template_variables(template.template)
	components = []
	if (template.get("header_type") or "").upper() == "DOCUMENT":
		header, _filename = document_header(doc, print_format)
		components.append(header)
	if variables:
		named = not all(v.isdigit() for v in variables)
		if named:
			params = [{"type": "text", "parameter_name": v, "text": template_value(doc, v)} for v in variables]
		else:
			fields = _lines(template.get("field_names"))
			if len(fields) < len(variables):
				frappe.throw(_("Template {0} uses numbered variables; list the matching fields in its Field Names.").format(template.name))
			params = [{"type": "text", "text": template_value(doc, f)} for f in fields[: len(variables)]]
		components.append({"type": "body", "parameters": params})
	return {
		"messaging_product": "whatsapp",
		"to": phone,
		"type": "template",
		"template": {
			"name": template.actual_name or template.template_name,
			"language": {"code": template.language_code},
			"components": components,
		},
	}


def _component(payload, kind):
	return next((c for c in payload["template"].get("components") or [] if c.get("type") == kind), {})


def render_template_text(template, payload):
	"""The message as the recipient reads it (header, body with its values, footer), for the conversation log."""
	params = _component(payload, "body").get("parameters") or []
	values = {p.get("parameter_name"): p["text"] for p in params if p.get("parameter_name")}
	positional = [p["text"] for p in params if not p.get("parameter_name")]

	def fill(match):
		key = match.group(1)
		if key.isdigit():
			index = int(key) - 1
			return positional[index] if 0 <= index < len(positional) else match.group(0)
		return values.get(key, match.group(0))

	attachment = ((_component(payload, "header").get("parameters") or [{}])[0].get("document") or {}).get("filename")
	parts = [
		template.get("header") if (template.get("header_type") or "TEXT").upper() == "TEXT" else (f"📎 {attachment}" if attachment else None),
		VARIABLE.sub(fill, template.template or ""),
		template.get("footer"),
	]
	return "\n".join(part.strip() for part in parts if part and part.strip())


def send_whatsapp(doctype, name, template, phones, print_format=None):
	from frappe.integrations.utils import make_post_request
	from frappe_whatsapp.utils import get_whatsapp_account

	doc = frappe.get_doc(doctype, name)
	tpl = frappe.get_doc("WhatsApp Templates", template)
	if (tpl.status or "").upper() != "APPROVED":
		frappe.log_error(f"Template {template} is {tpl.status}; nothing sent for {doctype} {name}", "WhatsApp Flow Notification")
		return
	account = get_whatsapp_account(account_type="outgoing")
	if not account:
		frappe.log_error("No default outgoing WhatsApp Account", "WhatsApp Flow Notification")
		return
	url = f"{account.url}/{account.version}/{account.phone_id}/messages"
	headers = {"authorization": f"Bearer {account.get_password('token')}", "content-type": "application/json"}
	for phone in phones:
		payload = build_template_payload(doc, tpl, phone, print_format)
		try:
			response = make_post_request(url, headers=headers, data=json.dumps(payload))
			params = _component(payload, "body").get("parameters") or []
			frappe.get_doc(
				{
					"doctype": "WhatsApp Message",
					"type": "Outgoing",
					"to": phone,
					"message": render_template_text(tpl, payload),
					"message_type": "Template",
					"message_id": response["messages"][0]["id"],
					"content_type": "document" if _component(payload, "header") else "text",
					"use_template": 1,
					"template": template,
					"template_parameters": json.dumps([p["text"] for p in params]),
					"reference_doctype": doctype,
					"reference_name": name,
					"whatsapp_account": account.name,
					"status": "Success",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"WhatsApp Flow Notification WhatsApp: {doctype} {name} → {phone}")
		frappe.db.commit()


# --------------------------------------------------------------------------
# Approve / Reject replies
# --------------------------------------------------------------------------
def on_whatsapp_message(doc, method=None):
	if doc.type != "Incoming" or doc.content_type != "button" or not doc.reply_to_message_id:
		return
	if not cint(frappe.db.get_single_value("WhatsApp Settings", "apply_whatsapp_approval_replies")):
		return
	try:
		apply_reply(doc)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "WhatsApp Approval Reply")


def apply_reply(msg):
	from frappe.model.workflow import apply_workflow, get_transitions

	sent = frappe.db.get_value(
		"WhatsApp Message",
		{"message_id": msg.reply_to_message_id, "type": "Outgoing"},
		["to", "reference_doctype", "reference_name"],
		as_dict=True,
	)
	if not sent or not sent.reference_doctype or not sent.reference_name:
		return
	sender = normalize_phone(msg.get("from"))
	# only the person the request was sent to may answer it
	if not sender or normalize_phone(sent.to) != sender:
		return _reply(msg, _("This approval request was not sent to your number."))
	user = user_for_phone(sender)
	if not user:
		return _reply(msg, _("Your number is not linked to an ERP user, so the action was not applied."))

	action = (msg.message or "").strip()
	original = frappe.session.user
	try:
		frappe.set_user(user)
		doc = frappe.get_doc(sent.reference_doctype, sent.reference_name)
		state_field = _state_field(doc.doctype)
		allowed = {t.action.lower(): t.action for t in get_transitions(doc)}
		if action.lower() not in allowed:
			return _reply(msg, _("{0} {1} is {2}; '{3}' is not available to you now.").format(doc.doctype, doc.name, doc.get(state_field), action))
		updated = apply_workflow(doc, allowed[action.lower()]) or doc
		doc.add_comment("Comment", _("{0} via WhatsApp by {1}").format(allowed[action.lower()], get_fullname(user)))
		frappe.db.commit()
		_reply(msg, _("Done: {0} {1} is now {2}.").format(doc.doctype, doc.name, updated.get(state_field)))
	finally:
		frappe.set_user(original)


def _state_field(doctype):
	from frappe.model.workflow import get_workflow_name

	workflow = get_workflow_name(doctype)
	return (workflow and frappe.get_cached_value("Workflow", workflow, "workflow_state_field")) or "workflow_state"


def user_for_phone(phone):
	last10 = phone[-10:]
	for emp in frappe.get_all("Employee", filters={"status": "Active", "user_id": ["is", "set"]}, fields=["user_id", "cell_number"]):
		if re.sub(r"\D", "", emp.cell_number or "")[-10:] == last10:
			return emp.user_id
	for user in frappe.get_all("User", filters={"enabled": 1, "mobile_no": ["is", "set"]}, fields=["name", "mobile_no"]):
		if re.sub(r"\D", "", user.mobile_no or "")[-10:] == last10:
			return user.name
	return None


def _reply(msg, text):
	"""Free-form reply inside the 24h window the approver just opened."""
	try:
		frappe.get_doc(
			{
				"doctype": "WhatsApp Message",
				"type": "Outgoing",
				"to": msg.get("from"),
				"message": text,
				"content_type": "text",
				"is_reply": 1,
				"reply_to_message_id": msg.message_id,
				"whatsapp_account": msg.whatsapp_account,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "WhatsApp Approval Reply")
