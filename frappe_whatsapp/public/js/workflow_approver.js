// Send for approval to one chosen approver.
//
// Every workflow button on a form goes through frappe.ui.form.States#handle_workflow_action. When the action moves a
// document to a step that others must approve, this asks which approver should get it first, and only that person is
// told by WhatsApp and email (see frappe_whatsapp/utils/approver_choice.py). If the check fails for any reason the
// action goes ahead as before: this can delay nothing and block nothing.

(function () {
	const API = "frappe_whatsapp.utils.approver_choice.";
	const SEARCH_FROM = 8; // a search box once there are this many approvers

	/** The people matching what was typed (name, user id or role). */
	function mfa_filter(users, text) {
		const q = (text || "").trim().toLowerCase();
		if (!q) return users;
		return users.filter((u) => `${u.full_name} ${u.user} ${u.email || ""} ${(u.roles || []).join(" ")}`.toLowerCase().includes(q));
	}

	function mfa_remember(key, value) {
		try { localStorage.setItem(key, value); } catch (e) { /* private window: fine */ }
	}

	function mfa_recall(key) {
		try { return localStorage.getItem(key); } catch (e) { return null; }
	}

	/** Resolves true when the action may go ahead, false when the sender backed out. */
	function mfa_ask(frm, action) {
		return new Promise((resolve) => {
			frappe
				.call({ method: API + "get_approver_choices", args: { doctype: frm.doctype, name: frm.docname, action }, freeze: false, silent: true })
				.then((r) => {
					const info = r.message || {};
					// nobody to choose between: the usual notification already reaches the one approver (or none)
					if (!info.required || (info.users || []).length < 2) return resolve(true);
					mfa_dialog(frm, action, info, resolve);
				})
				.catch(() => resolve(true));
		});
	}

	function mfa_dialog(frm, action, info, resolve) {
		const e = frappe.utils.escape_html;
		const memory = `mel_last_approver:${frm.doctype}:${action}`;
		let chosen = mfa_recall(memory);
		if (!info.users.some((u) => u.user === chosen)) chosen = null;
		let done = false;

		const dialog = new frappe.ui.Dialog({
			title: __(action),
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("Send for approval"),
			primary_action: () => {
				if (!chosen) {
					frappe.show_alert({ message: __("Choose an approver first."), indicator: "orange" });
					return;
				}
				dialog.get_primary_btn().prop("disabled", true).text(__("Sending..."));
				frappe
					.call({ method: API + "choose_approver", args: { doctype: frm.doctype, name: frm.docname, action, approver: chosen }, freeze: false })
					.then((r) => {
						mfa_remember(memory, chosen);
						done = true;
						dialog.hide();
						const who = (r.message || {}).full_name || chosen;
						frappe.show_alert({ message: __("Sending to {0} for approval", [e(who)]), indicator: "green" });
						resolve(true);
					})
					.catch(() => dialog.get_primary_btn().prop("disabled", false).text(__("Send for approval")));
			},
			secondary_action_label: __("Cancel"),
			secondary_action: () => dialog.hide(),
		});
		dialog.onhide = () => { if (!done) resolve(false); };

		const render = (text) => {
			const shown = mfa_filter(info.users, text);
			const rows = shown.map((u) => `
				<label class="mfa-option${u.user === chosen ? " is-chosen" : ""}">
					<input type="radio" name="mfa-approver" value="${e(u.user)}" ${u.user === chosen ? "checked" : ""}>
					<span class="mfa-who">
						<span class="mfa-name">${e(u.full_name)}</span>
						<span class="mfa-meta">${e(u.email || u.user)}</span>
						<span class="mfa-roles">${(u.roles || []).map((r) => `<span class="mfa-role">${e(r)}</span>`).join("")}</span>
					</span>
					<span class="mfa-wa ${u.whatsapp ? "mfa-wa-yes" : "mfa-wa-no"}">${u.whatsapp ? __("WhatsApp and email") : __("Email only: no mobile number")}</span>
				</label>`).join("");
			dialog.fields_dict.body.$wrapper.find(".mfa-list").html(rows || `<p class="text-muted mfa-none" role="status">${__("No approver matches.")}</p>`);
		};

		const search = info.users.length >= SEARCH_FROM
			? `<input type="search" class="form-control input-sm mfa-search" placeholder="${__("Search name or role")}" aria-label="${__("Search approvers")}">` : "";
		dialog.fields_dict.body.$wrapper.html(`
			<div class="mfa">
				<p class="mfa-intro">${__("Choose who should approve {0} {1}. Only they will get the WhatsApp message and the email.", [__(frm.doctype), `<strong>${e(frm.docname)}</strong>`])}</p>
				${search}
				<div class="mfa-list" role="radiogroup" aria-label="${__("Approver")}"></div>
			</div>`);
		render("");
		const body = dialog.fields_dict.body.$wrapper;
		const ready = () => dialog.get_primary_btn().prop("disabled", !chosen); // nothing to send until someone is picked
		body.on("change", "input[name=mfa-approver]", (ev) => {
			chosen = ev.target.value;
			ready();
			body.find(".mfa-option").removeClass("is-chosen");
			$(ev.target).closest(".mfa-option").addClass("is-chosen");
		});
		body.on("input", ".mfa-search", (ev) => render(ev.target.value));
		dialog.show();
		ready();
		setTimeout(() => body.find(chosen ? "input:checked" : ".mfa-search, input[name=mfa-approver]").first().trigger("focus"), 200);
	}

	function patch() {
		const States = frappe.ui && frappe.ui.form && frappe.ui.form.States;
		if (!States || States.prototype.__mfa_patched) return;
		const original = States.prototype.handle_workflow_action;
		States.prototype.handle_workflow_action = function (transition) {
			mfa_ask(this.frm, transition.action).then((go) => { if (go) original.call(this, transition); });
		};
		States.prototype.__mfa_patched = true;
	}

	// the form classes may load after this file: patch now, and again the first time a form opens
	patch();
	$(document).on("form-refresh", patch);
	window.mfa_filter = mfa_filter; // for the checks in tests
})();
