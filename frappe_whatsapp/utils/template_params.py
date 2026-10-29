"""Sending an approved template by hand (Send Template dialog, Command Center).

The template body says how many variables Meta expects and what they are called, so the
parameters are built from it instead of from a hand-typed list, and a Meta rejection is
turned into a message that says what to change. Notifications build their own payloads
and do not use this module.
"""

import frappe
from frappe import _

from frappe_whatsapp.utils.contact_name import display_name
from frappe_whatsapp.utils.flow_notifications import _template_variables, template_value

# variables that name the person being messaged; when no document is given they come from the number
PERSON_VARIABLES = {"customer_name", "lead_name", "party_name", "employee_name", "supplier_name", "contact_name", "full_name", "first_name"}
DOC_ATTRIBUTES = ("name", "owner", "modified_by", "creation", "modified")


def body_variables(template):
	return _template_variables(template.template)


def is_named(variables):
	return bool(variables) and not all(v.isdigit() for v in variables)


def named_parameters(variables, doc, phone, template_label):
	"""One `{parameter_name, text}` per variable of a named template, filled from the document the
	message is sent from; when there is none, person variables come from whoever owns the number."""
	values, missing = [], []
	for variable in variables:
		if doc is not None and (variable in DOC_ATTRIBUTES or doc.meta.has_field(variable) or doc.get(variable) is not None):
			values.append(template_value(doc, variable))
		elif variable in PERSON_VARIABLES and display_name(phone):
			values.append(display_name(phone))
		else:
			missing.append(variable)
	if missing:
		where = _("Open the {0} it belongs to and send the template from there.").format(doc.doctype) if doc is not None else _("Send it from the document it belongs to, so the values can be read from it.")
		frappe.throw(
			_("Template {0} needs {1} value(s): {2}. No value could be found for: {3}. {4}").format(
				template_label, len(variables), ", ".join(variables), ", ".join(missing), where
			),
			title=_("Template values missing"),
		)
	return [{"type": "text", "parameter_name": v, "text": text} for v, text in zip(variables, values)], values


def numbered_fields_error(template_label, variables):
	frappe.throw(
		_("Template {0} has {1} numbered variable(s) ({2}) but no fields are listed for them. Add the matching field names, in order, to the template's Field Names.").format(
			template_label, len(variables), ", ".join("{{" + v + "}}" for v in variables)
		),
		title=_("Template values missing"),
	)


# what Meta's error codes mean for the person sending (built on use so the wording is translated)
def _friendly():
	return {
		131026: _("The number is not on WhatsApp, or cannot receive this message."),
		131030: _("This number is not on the allowed list for the WhatsApp account (test numbers must be added in Meta first)."),
		131047: _("More than 24 hours since this person last wrote, so only an approved template can be sent."),
		131049: _("Meta held this message back to keep the quality of the number's conversations. Try again later."),
		131056: _("Too many messages sent to this number in a short time. Wait a little and try again."),
		132001: _("The template name or language does not exist in Meta. Sync the templates and check that it is approved."),
		132005: _("The filled-in message is too long for the template."),
		132007: _("Meta refused the message content because it breaks their template policy."),
		132012: _("A value does not match the type the template expects. Values must not be empty or contain new lines."),
		132015: _("This template is paused by Meta because of poor quality. Use another template or edit it in Meta."),
		132016: _("This template is disabled by Meta. Use another template."),
		133010: _("The phone number is not registered with WhatsApp Business yet."),
		190: _("The WhatsApp account token has expired. Add a new token in the WhatsApp Account."),
	}


def friendly_error(res, data, template_name=None):
	"""Plain-language text for a Meta error, with Meta's own words kept underneath."""
	code = res.get("code")
	details = (res.get("error_data") or {}).get("details") or res.get("message") or res.get("Error") or ""
	sent = 0
	for component in (data.get("template") or {}).get("components", []):
		if component.get("type") == "body":
			sent = len(component.get("parameters") or [])
	if code == 132000:
		expected = None
		if template_name and frappe.db.exists("WhatsApp Templates", template_name):
			expected = body_variables(frappe.get_doc("WhatsApp Templates", template_name))
		if expected is not None:
			headline = _("Template {0} expects {1} value(s) ({2}) but {3} were sent.").format(template_name, len(expected), ", ".join(expected) or "-", sent)
			advice = _("Fill every variable, or list the matching fields in the template's Field Names.")
		else:
			headline = _("The number of values sent ({0}) does not match what the template expects.").format(sent)
			advice = _("Check the variables in the template and the values being sent.")
		return f"{headline} {advice}", details
	return _friendly().get(code) or details or _("WhatsApp could not send this message."), details
