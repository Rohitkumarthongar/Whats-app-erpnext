frappe.ui.form.on('WhatsApp Settings', {
 refresh(frm) {
   frm.add_custom_button(__('Open Command Center'), () => frappe.set_route('whatsapp-command-center'));
   frm.add_custom_button(__('Open Conversations'), () => frappe.set_route('List','WhatsApp Conversation'), __('Operations'));
   frm.add_custom_button(__('Automation Rules'), () => frappe.set_route('List','WhatsApp Automation Rule'), __('Operations'));
   frm.add_custom_button(__('Consent Registry'), () => frappe.set_route('List','WhatsApp Consent'), __('Operations'));
 }
});
