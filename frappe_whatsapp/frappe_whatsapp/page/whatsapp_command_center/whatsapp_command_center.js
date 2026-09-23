frappe.pages["whatsapp-command-center"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("WhatsApp Command Center"),
    single_column: true,
  });
  wrapper.whatsapp_center = new WhatsAppCommandCenter(page);
};
class WhatsAppCommandCenter {
  constructor(page) {
    this.page = page;
    this.selected = null;
    this.make();
    this.load();
  }
  make() {
    $(this.page.body).html(`<div class="wa-center">
      <nav class="wa-sidebar">
        <button data-view="dashboard" class="active"><span>${__("Dashboard")}</span></button>
        <button data-view="inbox"><span>${__("Inbox")}</span></button>
        <button data-view="campaigns" class="wa-nav-optional" data-flag="enable_campaigns"><span>${__("Campaigns")}</span></button>
        <button data-view="automation" class="wa-nav-optional" data-flag="enable_automation"><span>${__("Automation")}</span></button>
        <button data-view="settings"><span>${__("Settings")}</span></button>
      </nav>
      <div class="wa-main"><div class="wa-content"><div class="wa-loading">${__("Loading WhatsApp workspace...")}</div></div></div></div>`);
    this.page.body.on("click", ".wa-sidebar button", (e) => {
      this.page.body.find(".wa-sidebar button").removeClass("active");
      $(e.currentTarget).addClass("active");
      this.render($(e.currentTarget).data("view"));
    });
  }
  async load() {
    const r = await frappe.call(
      "frappe_whatsapp.frappe_whatsapp.api.command_center.get_boot_data",
    );
    this.data = r.message || {};
    // Campaigns / Automation are advanced surfaces most teams don't need in
    // the main nav — show them only when turned on in WhatsApp Settings.
    this.page.body.find(".wa-nav-optional").each((_, el) => {
      const flag = $(el).data("flag");
      $(el).toggle(!!(this.data.settings || {})[flag]);
    });
    this.render("dashboard");
  }
  render(view) {
    if (!this.data) return;
    const fn = this[`render_${view}`] || this.render_dashboard;
    this.page.body.find(".wa-main").toggleClass("wa-main-flush", view === "inbox");
    this.page.body.find(".wa-content").html(fn.call(this));
    this.bind(view);
  }
  render_dashboard() {
    const k = this.data.kpis || {};
    return `<div class="wa-grid kpis">${[
      ["Open Conversations", k.open_conversations || 0],
      ["Unread Messages", k.unread_messages || 0],
      ["Messages Today", k.messages_today || 0],
      ["SLA Breached", k.sla_breached || 0],
    ]
      .map(
        (x) =>
          `<div class="wa-card"><span>${x[0]}</span><strong>${x[1]}</strong></div>`,
      )
      .join(
        "",
      )}</div><div class="wa-grid two"><div class="wa-card"><h3>Recent Conversations</h3>${this.conversation_list(this.data.conversations || [])}</div><div class="wa-card"><h3>Delivery Overview</h3><div class="wa-bars">${Object.entries(
      this.data.delivery || {},
    )
      .map(
        ([a, b]) =>
          `<div><label>${a}<b>${b}</b></label><progress value="${b}" max="${Math.max(
            1,
            Object.values(this.data.delivery || {}).reduce((x, y) => x + y, 0),
          )}"></progress></div>`,
      )
      .join("")}</div></div></div>`;
  }
  conversation_list(rows) {
    return rows.length
      ? rows
          .map(
            (x) =>
              `<div class="wa-conv" data-name="${x.name}"><div class="avatar">${(x.customer_name || x.phone_number || "?")[0]}</div><div><b>${frappe.utils.escape_html(x.customer_name || x.phone_number)}</b><small>${frappe.utils.escape_html(x.last_message || "")}</small></div><span>${x.unread_count || ""}</span></div>`,
          )
          .join("")
      : `<div class="wa-empty">No conversations yet. Incoming messages will appear here.</div>`;
  }
  render_inbox() {
    return `<div class="wa-inbox"><aside><div class="wa-search"><input placeholder="Search conversations"></div>${this.conversation_list(this.data.conversations || [])}</aside><main><div class="wa-empty large">Select a conversation to open messages and ERPNext customer context.</div></main><section><h3>ERPNext Context</h3><p>Contact, Lead, Customer, Issue, quotations, orders and invoices appear here after selecting a conversation.</p></section></div>`;
  }
  render_campaigns() {
    return `<div class="wa-grid two"><div class="wa-card"><h3>Campaign Center</h3><p>Create template campaigns, segment recipients, enforce consent and rate limits, and track delivery.</p><button class="btn btn-primary" data-doctype="Bulk WhatsApp Message">New Campaign</button></div><div class="wa-card"><h3>Compliance</h3><p>Opt-in required: <b>${this.data.settings.require_opt_in ? "Yes" : "No"}</b></p><p>Batch size: <b>${this.data.settings.campaign_batch_size || 50}</b></p><p>Rate/minute: <b>${this.data.settings.campaign_rate_per_minute || 60}</b></p></div></div>`;
  }
  render_automation() {
    return `<div class="wa-card"><h3>Automation & Bot Rules</h3><p>Build keyword replies, routing, issue creation, lead creation and document-event actions.</p><button class="btn btn-primary" data-doctype="WhatsApp Automation Rule">Open Automation Rules</button><div class="wa-flow"><span>Incoming Message</span><i>→</i><span>Match Rule</span><i>→</i><span>ERP Action</span><i>→</i><span>WhatsApp Reply</span></div></div>`;
  }
  render_settings() {
    const s = this.data.settings || {};
    return `<div class="wa-card"><h3>Feature Controls</h3><div class="wa-settings">${Object.entries(
      s,
    )
      .filter(
        (x) =>
          x[0].startsWith("enable_") ||
          ["require_opt_in", "mask_phone_numbers"].includes(x[0]),
      )
      .map(
        ([k, v]) =>
          `<label><input type="checkbox" ${v ? "checked" : ""} disabled><span>${frappe.model.unscrub(k)}</span></label>`,
      )
      .join(
        "",
      )}</div><button class="btn btn-primary" data-doctype="WhatsApp Settings">Open Full Settings</button></div>`;
  }
  bind(view) {
    this.page.body
      .find("[data-doctype]")
      .on("click", (e) =>
        frappe.set_route("List", $(e.currentTarget).data("doctype")),
      );
    this.page.body
      .find(".wa-conv")
      .on("click", (e) =>
        this.open_conversation($(e.currentTarget).data("name")),
      );
  }
  async open_conversation(name) {
    const r = await frappe.call(
      "frappe_whatsapp.frappe_whatsapp.api.command_center.get_conversation",
      { conversation: name },
    );
    const d = r.message || {};
    const messages = (d.messages || [])
      .map((m) => {
        let content = '';
        let classes = ["bubble", m.type === "Outgoing" ? "out" : "in"];

        if (m.attach) {
          classes.push("attachment");
          let isImg = m.attach.match(/\.(jpeg|jpg|png|gif|webp)$/i) || m.content_type === "image";
          if (isImg) {
            content += `<img src="${m.attach}" class="wa-img" onclick="window.open('${m.attach}', '_blank')">`;
          } else {
            content += `<a href="${m.attach}" target="_blank" class="wa-doc">
              <svg viewBox="0 0 24 24" width="24" height="24"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"></path></svg>
              Attachment
            </a>`;
          }
          if (m.message) content += `<div class="bubble-text">${frappe.utils.escape_html(m.message)}</div>`;
        } else if (m.template) {
           classes.push("template");
           content += `<div class="bubble-text"><i>Template: ${m.template}</i><br>${frappe.utils.escape_html(m.message || "")}</div>`;
        } else {
          content += `<div class="bubble-text">${frappe.utils.escape_html(m.message || m.content_type || "")}</div>`;
        }

        let time = frappe.datetime.global_date_format(m.creation) + ' ' + frappe.datetime.get_time(m.creation).substring(0, 5);
        let readIcon = m.status === "read" ? "read" : "";
        let meta = `<div class="meta"><span>${time}</span>`;

        if (m.type === "Outgoing") {
          meta += `<svg class="${readIcon}" viewBox="0 0 16 11" width="16" height="11"><path fill="currentColor" d="M11.8 1.6l-5.6 5.6-2.2-2.2-1.4 1.4 3.6 3.6 7-7-1.4-1.4z"></path></svg>`;
        }
        meta += `</div>`;

        return `<div class="${classes.join(' ')}">${content}${meta}</div>`;
      })
      .join("");
    this.page.body
      .find(".wa-inbox main")
      .html(
        `<div class="chat-head"><b>${d.conversation.customer_name || d.conversation.phone_number}</b><button class="btn btn-xs btn-default wa-assign">Assign</button></div><div class="chat-body">${messages || '<div class="wa-empty">No messages</div>'}</div><div class="chat-send">
    <div class="chat-actions">
        <button class="wa-attach" title="Attach file" style="margin-right: -10px;">
            <svg viewBox="0 0 24 24" width="24" height="24" class=""><path fill="currentColor" d="M1.816 15.556v.002c0 1.502.584 2.912 1.646 3.972s2.472 1.647 3.974 1.647a5.58 5.58 0 0 0 3.972-1.645l9.547-9.548c.769-.768 1.147-1.767 1.058-2.817-.079-.968-.548-1.927-1.319-2.698-1.594-1.592-4.068-1.711-5.517-.262l-7.916 7.915c-.881.881-.792 2.25.214 3.261.959.958 2.423 1.053 3.263.215l5.511-5.512c.28-.28.267-.722.053-.936l-.244-.244c-.191-.191-.567-.349-.957.04l-5.506 5.506c-.18.18-.635.127-.976-.214-.098-.097-.576-.613-.213-.973l7.915-7.917c.818-.817 2.267-.699 3.23.262.5.501.802 1.1.849 1.685.051.573-.156 1.111-.589 1.543l-9.547 9.549a3.97 3.97 0 0 1-2.829 1.171 3.975 3.975 0 0 1-2.83-1.173 3.973 3.973 0 0 1-1.172-2.828c0-1.071.415-2.076 1.172-2.83l7.209-7.211c.157-.157.264-.579.028-.814L11.5 4.36a.57.57 0 0 0-.834.018l-7.205 7.207a5.577 5.577 0 0 0-1.645 3.971z"></path></svg>
        </button>
        <button class="wa-template-btn" title="Send template">
            <svg viewBox="0 0 24 24" width="24" height="24" class=""><path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM5 19V5h14v14H5zm2-6h10v2H7v-2zm0-4h10v2H7V9z"></path></svg>
        </button>
    </div>
    <input placeholder="Type a message">
    <button class="btn btn-primary">Send</button>
</div>`,
      );
    this.page.body
      .find(".wa-inbox section")
      .html(
        `<h3>ERPNext Context</h3><p><b>Phone:</b> ${d.conversation.phone_number}</p><p><b>Status:</b> ${d.conversation.status}</p><p><b>Assigned:</b> ${d.conversation.assigned_to || "Unassigned"}</p><button class="btn btn-sm btn-default wa-issue">Create Issue</button>`,
      );
    this.page.body.find(".chat-send > button").on("click", async () => {
      let input = this.page.body.find(".chat-send input");
      if (!input.val()) return;
      await frappe.call(
        "frappe_whatsapp.frappe_whatsapp.api.command_center.send_text",
        { conversation: name, message: input.val() },
      );
      input.val("");
      this.open_conversation(name);
    });
    this.page.body.find(".chat-actions .wa-template-btn").on("click", () => {
      let dialog = new frappe.ui.Dialog({
        title: __('Select Template'),
        fields: [
          {
            label: 'Template',
            fieldname: 'template',
            fieldtype: 'Link',
            options: 'WhatsApp Templates',
            reqd: 1,
            get_query: () => {
              return { filters: { status: 'APPROVED' } };
            }
          }
        ],
        primary_action_label: __('Send'),
        primary_action: async (values) => {
          dialog.hide();
          await frappe.call(
            "frappe_whatsapp.frappe_whatsapp.api.command_center.send_text",
            { conversation: name, template: values.template }
          );
          this.open_conversation(name);
        }
      });
      dialog.show();
    });

    this.page.body.find(".chat-actions .wa-attach").on("click", () => {
      new frappe.ui.FileUploader({
        doctype: "WhatsApp Conversation",
        docname: name,
        on_success: async (file_doc) => {
          let content_type = "document";
          if (file_doc.file_url.match(/\.(jpeg|jpg|png|gif|webp)$/i)) content_type = "image";
          else if (file_doc.file_url.match(/\.(mp4|avi|mov)$/i)) content_type = "video";
          else if (file_doc.file_url.match(/\.(mp3|ogg|wav)$/i)) content_type = "audio";

          await frappe.call(
            "frappe_whatsapp.frappe_whatsapp.api.command_center.send_text",
            { conversation: name, attach: file_doc.file_url, content_type: content_type }
          );
          this.open_conversation(name);
        }
      });
    });

    this.page.body
      .find(".wa-issue")
      .on("click", () =>
        frappe
          .call(
            "frappe_whatsapp.frappe_whatsapp.api.command_center.create_issue",
            { conversation: name },
          )
          .then((r) => frappe.set_route("Form", "Issue", r.message)),
      );
  }
}
