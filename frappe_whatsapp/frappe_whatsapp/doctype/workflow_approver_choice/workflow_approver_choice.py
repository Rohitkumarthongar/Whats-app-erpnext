from frappe.model.document import Document


class WorkflowApproverChoice(Document):
	"""Who the sender picked to approve a document after a workflow action. Written only by
	frappe_whatsapp.utils.approver_choice.choose_approver, read when the approval email and the
	WhatsApp message are addressed."""
