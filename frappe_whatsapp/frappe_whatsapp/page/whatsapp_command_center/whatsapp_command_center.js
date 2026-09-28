frappe.pages["whatsapp-command-center"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("WhatsApp Command Center"),
    single_column: true,
  });
  wrapper.whatsapp_center = new WhatsAppCommandCenter(page);
};

const STATUS_OPTIONS = ["Open", "Pending", "Resolved", "Closed"];
const PRIORITY_OPTIONS = ["Low", "Medium", "High", "Urgent"];
const MODULE_LINKS = [
  { label: "Accounts", doctype: "WhatsApp Account" },
  { label: "Automation Rules", doctype: "WhatsApp Automation Rule" },
  { label: "Campaigns", doctype: "Bulk WhatsApp Message" },
  { label: "Consent Log", doctype: "WhatsApp Consent" },
  { label: "Conversations", doctype: "WhatsApp Conversation" },
  { label: "Flows", doctype: "WhatsApp Flow" },
  { label: "Messages", doctype: "WhatsApp Message" },
  { label: "Notification Log", doctype: "WhatsApp Notification Log" },
  { label: "Notifications", doctype: "WhatsApp Notification" },
  { label: "Profiles", doctype: "WhatsApp Profiles" },
  { label: "Recipient Lists", doctype: "WhatsApp Recipient List" },
  { label: "Templates", doctype: "WhatsApp Templates" },
].sort((a, b) => a.label.localeCompare(b.label));
const esc = (value) => frappe.utils.escape_html(value == null ? "" : String(value));

class WhatsAppCommandCenter {
  constructor(page) {
    this.page = page;
    this.selected = null;
    this.current_view = "dashboard";
    this.inbox_filter = { status: "All", q: "", unread_only: false, sla_only: false };
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
        ${MODULE_LINKS.map(
          (m) =>
            `<button class="wa-sidebar-link" data-doctype="${esc(m.doctype)}" ${m.single ? 'data-single="1"' : ""}><span>${esc(m.label)}</span></button>`,
        ).join("")}
      </nav>
      <div class="wa-main"><div class="wa-content"><div class="wa-loading">${__("Loading WhatsApp workspace...")}</div></div></div></div>`);
    this.page.body.on("click", ".wa-sidebar button[data-view]", (e) => {
      this.activate_nav($(e.currentTarget).data("view"));
      this.render($(e.currentTarget).data("view"));
    });
    this.page.body.on("click", ".wa-sidebar-link", (e) => {
      const $el = $(e.currentTarget);
      const doctype = $el.data("doctype");
      if ($el.data("single")) frappe.set_route("Form", doctype);
      else frappe.set_route("List", doctype);
    });
  }
  activate_nav(view) {
    this.page.body.find(".wa-sidebar button[data-view]").removeClass("active");
    this.page.body.find(`.wa-sidebar button[data-view="${view}"]`).addClass("active");
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
    this.render(this.current_view || "dashboard");
  }
  render(view) {
    if (!this.data) return;
    this.current_view = view;
    const fn = this[`render_${view}`] || this.render_dashboard;
    this.page.body.find(".wa-main").toggleClass("wa-main-flush", view === "inbox");
    this.page.body.find(".wa-content").html(fn.call(this));
    this.bind(view);
  }

  avatar_color(seed) {
    const s = String(seed || "?");
    let hash = 0;
    for (let i = 0; i < s.length; i++) hash = s.charCodeAt(i) + ((hash << 5) - hash);
    const hue = Math.abs(hash) % 360;
    return `hsl(${hue}, 60%, 88%)`;
  }
  relative_time(value) {
    if (!value) return "";
    try {
      return frappe.datetime.comment_when(value);
    } catch (e) {
      return frappe.datetime.str_to_user(value) || "";
    }
  }
  goto_conversation(name) {
    if (this.current_view !== "inbox") {
      this.activate_nav("inbox");
      this.render("inbox");
    }
    this.open_conversation(name);
  }
  handle_kpi_click(key) {
    const map = {
      open_conversations: { status: "Open" },
      unread_messages: { unread_only: true },
      sla_breached: { sla_only: true },
      messages_today: {},
    };
    this.inbox_filter = Object.assign(
      { status: "All", q: "", unread_only: false, sla_only: false },
      map[key] || {},
    );
    this.activate_nav("inbox");
    this.render("inbox");
  }
  new_message_dialog() {
    const dialog = new frappe.ui.Dialog({
      title: __("New Message"),
      fields: [
        {
          label: __("Phone Number"),
          fieldname: "phone_number",
          fieldtype: "Data",
          reqd: 1,
          description: __("Include the country code, e.g. 91XXXXXXXXXX"),
        },
        { label: __("Contact Name"), fieldname: "customer_name", fieldtype: "Data" },
        {
          label: __("Message"),
          fieldname: "message",
          fieldtype: "Small Text",
          description: __("Leave blank to start the conversation with an approved template instead"),
        },
        {
          label: __("Or send an approved template"),
          fieldname: "template",
          fieldtype: "Link",
          options: "WhatsApp Templates",
          get_query: () => ({ filters: { status: "APPROVED" } }),
        },
      ],
      primary_action_label: __("Send"),
      primary_action: async (values) => {
        if (!(values.message || "").trim() && !values.template) {
          frappe.msgprint(__("Enter a message or choose a template"));
          return;
        }
        dialog.hide();
        const r = await frappe.call({
          method: "frappe_whatsapp.frappe_whatsapp.api.command_center.start_conversation",
          args: {
            phone_number: values.phone_number,
            customer_name: values.customer_name,
            message: values.message,
            template: values.template,
          },
        });
        await this.load();
        this.goto_conversation(r.message.conversation);
      },
    });
    dialog.show();
  }

  conversation_list(rows) {
    if (!rows.length) return `<div class="wa-empty">${__("No conversations match this view.")}</div>`;
    return rows
      .map((x) => {
        const initial = (x.customer_name || x.phone_number || "?")[0].toUpperCase();
        const classes = ["wa-conv"];
        if (x.name === this.selected) classes.push("active");
        if (x.unread_count) classes.push("unread");
        return `<div class="${classes.join(" ")}" data-name="${esc(x.name)}">
          <div class="avatar" style="background:${this.avatar_color(x.customer_name || x.phone_number)}">${esc(initial)}</div>
          <div class="wa-conv-body">
            <div class="wa-conv-top"><b>${esc(x.customer_name || x.phone_number)}</b><span class="wa-conv-time">${this.relative_time(x.last_message_at)}</span></div>
            <div class="wa-conv-bottom"><small>${esc(x.last_message || "")}</small>${x.unread_count ? `<span class="wa-badge">${x.unread_count}</span>` : ""}</div>
          </div>
          <div class="wa-conv-flags">
            ${x.priority && x.priority !== "Low" ? `<i class="wa-dot priority-${x.priority.toLowerCase()}" title="${esc(x.priority)}"></i>` : ""}
            ${x.sla_breached ? `<i class="wa-dot sla" title="${__("SLA breached")}"></i>` : ""}
          </div>
        </div>`;
      })
      .join("");
  }
  filtered_conversations() {
    const f = this.inbox_filter;
    const q = (f.q || "").toLowerCase().trim();
    return (this.data.conversations || []).filter((c) => {
      if (f.status !== "All" && (c.status || "") !== f.status) return false;
      if (f.unread_only && !(c.unread_count > 0)) return false;
      if (f.sla_only && !c.sla_breached) return false;
      if (q) {
        const hay = `${c.customer_name || ""} ${c.phone_number || ""} ${c.last_message || ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  render_dashboard() {
    const k = this.data.kpis || {};
    const tiles = [
      ["open_conversations", __("Open Conversations"), k.open_conversations || 0],
      ["unread_messages", __("Unread Messages"), k.unread_messages || 0],
      ["messages_today", __("Messages Today"), k.messages_today || 0],
      ["sla_breached", __("SLA Breached"), k.sla_breached || 0],
    ];
    return `<div class="wa-grid kpis">${tiles
      .map(
        ([key, label, value]) =>
          `<button class="wa-card wa-kpi" data-kpi="${key}"><span>${label}</span><strong>${value}</strong></button>`,
      )
      .join(
        "",
      )}</div><div class="wa-card wa-recent-full"><h3>${__("Recent Conversations")}</h3>${this.conversation_list((this.data.conversations || []).slice(0, 8))}</div>`;
  }
  active_filter_label() {
    if (this.inbox_filter.unread_only) return __("Unread");
    if (this.inbox_filter.sla_only) return __("SLA breached");
    if (this.inbox_filter.status !== "All") return __(this.inbox_filter.status);
    return null;
  }
  render_inbox() {
    const label = this.active_filter_label();
    return `<div class="wa-inbox">
      <aside>
        <div class="wa-aside-head">
          <div class="wa-search"><input placeholder="${__("Search conversations")}" value="${esc(this.inbox_filter.q)}"></div>
          <button class="wa-new-message">${__("+ New Message")}</button>
        </div>
        ${
          label
            ? `<div class="wa-active-filter"><span>${__("Filtered by")}: ${label}</span><button class="wa-clear-filter" title="${__("Clear")}">${__("Clear")}</button></div>`
            : ""
        }
        <div class="wa-conv-list">${this.conversation_list(this.filtered_conversations())}</div>
      </aside>
      <main>${this.selected ? "" : `<div class="wa-empty large">${__("Select a conversation to open messages and ERPNext customer context.")}</div>`}</main>
      <section><h3>${__("ERPNext Context")}</h3><p>${__("Contact, Lead, Customer, Issue, quotations, orders and invoices appear here after selecting a conversation.")}</p></section>
    </div>`;
  }
  refresh_inbox_list() {
    this.page.body.find(".wa-conv-list").html(this.conversation_list(this.filtered_conversations()));
    this.page.body
      .find(".wa-conv-list .wa-conv")
      .on("click", (e) => this.goto_conversation($(e.currentTarget).data("name")));
  }
  render_campaigns() {
    const s = this.data.settings || {};
    return `<div class="wa-grid two"><div class="wa-card"><h3>${__("Campaign Center")}</h3><p>${__("Create template campaigns, segment recipients, enforce consent and rate limits, and track delivery.")}</p><button class="btn btn-primary" data-doctype="Bulk WhatsApp Message">${__("New Campaign")}</button></div><div class="wa-card"><h3>${__("Compliance")}</h3><p>${__("Opt-in required")}: <b>${s.require_opt_in ? __("Yes") : __("No")}</b></p><p>${__("Batch size")}: <b>${s.campaign_batch_size || 50}</b></p><p>${__("Rate/minute")}: <b>${s.campaign_rate_per_minute || 60}</b></p></div></div>`;
  }
  render_automation() {
    return `<div class="wa-card"><h3>${__("Automation & Bot Rules")}</h3><p>${__("Build keyword replies, routing, issue creation, lead creation and document-event actions.")}</p><button class="btn btn-primary" data-doctype="WhatsApp Automation Rule">${__("Open Automation Rules")}</button><div class="wa-flow"><span>${__("Incoming Message")}</span><i>→</i><span>${__("Match Rule")}</span><i>→</i><span>${__("ERP Action")}</span><i>→</i><span>${__("WhatsApp Reply")}</span></div></div>`;
  }
  render_settings() {
    const s = this.data.settings || {};
    return `<div class="wa-card"><h3>${__("Feature Controls")}</h3><div class="wa-settings">${Object.entries(
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
      )}</div><button class="btn btn-primary" data-doctype="WhatsApp Settings" data-single="1">${__("Open Full Settings")}</button></div>`;
  }

  bind(view) {
    this.page.body
      .find(".wa-content button[data-doctype]")
      .on("click", (e) => {
        const $el = $(e.currentTarget);
        const doctype = $el.data("doctype");
        if ($el.data("single")) frappe.set_route("Form", doctype);
        else frappe.set_route("List", doctype);
      });
    this.page.body
      .find(".wa-conv")
      .on("click", (e) =>
        this.goto_conversation($(e.currentTarget).data("name")),
      );
    this.page.body
      .find(".wa-kpi")
      .on("click", (e) => this.handle_kpi_click($(e.currentTarget).data("kpi")));

    if (view === "inbox") {
      this.page.body.find(".wa-new-message").on("click", () => this.new_message_dialog());
      let debounce;
      this.page.body.find(".wa-search input").on("input", (e) => {
        const value = e.target.value;
        clearTimeout(debounce);
        debounce = setTimeout(() => {
          this.inbox_filter.q = value;
          this.refresh_inbox_list();
        }, 200);
      });
      this.page.body.find(".wa-clear-filter").on("click", () => {
        this.inbox_filter.status = "All";
        this.inbox_filter.unread_only = false;
        this.inbox_filter.sla_only = false;
        this.render("inbox");
      });
    }
  }

  async open_conversation(name) {
    this.selected = name;
    const r = await frappe.call(
      "frappe_whatsapp.frappe_whatsapp.api.command_center.get_conversation",
      { conversation: name },
    );
    const d = r.message || {};
    const conv = d.conversation || {};
    this.page.body.find(".wa-conv").removeClass("active");
    this.page.body.find(`.wa-conv[data-name="${esc(name)}"]`).addClass("active");

    const messages = (d.messages || [])
      .map((m) => {
        let content = '';
        let classes = ["bubble", m.type === "Outgoing" ? "out" : "in"];

        if (m.attach) {
          classes.push("attachment");
          let isImg = m.attach.match(/\.(jpeg|jpg|png|gif|webp)$/i) || m.content_type === "image";
          if (isImg) {
            content += `<img src="${esc(m.attach)}" class="wa-img" data-open="${esc(m.attach)}">`;
          } else {
            content += `<a href="${esc(m.attach)}" target="_blank" class="wa-doc">
              <svg viewBox="0 0 24 24" width="24" height="24"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"></path></svg>
              ${__("Attachment")}
            </a>`;
          }
          if (m.message) content += `<div class="bubble-text">${esc(m.message)}</div>`;
        } else if (m.template) {
           classes.push("template");
           content += `<div class="bubble-text"><i>${__("Template")}: ${esc(m.template)}</i><br>${esc(m.message || "")}</div>`;
        } else {
          content += `<div class="bubble-text">${esc(m.message || m.content_type || "")}</div>`;
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

    const displayName = conv.customer_name || conv.phone_number;
    this.page.body
      .find(".wa-inbox main")
      .html(
        `<div class="chat-head">
          <div class="avatar" style="background:${this.avatar_color(displayName)}">${esc((displayName || "?")[0].toUpperCase())}</div>
          <b>${esc(displayName)}</b>
          <select class="wa-status-select" title="${__("Status")}">${STATUS_OPTIONS.map((s) => `<option value="${s}" ${s === conv.status ? "selected" : ""}>${__(s)}</option>`).join("")}</select>
          <select class="wa-priority-select" title="${__("Priority")}">${PRIORITY_OPTIONS.map((s) => `<option value="${s}" ${s === (conv.priority || "Medium") ? "selected" : ""}>${__(s)}</option>`).join("")}</select>
          <button class="btn btn-xs btn-default wa-assign">${conv.assigned_to ? __("Reassign") : __("Assign")}</button>
        </div>
        <div class="chat-body">${messages || `<div class="wa-empty">${__("No messages")}</div>`}</div>
        ${
          conv.status === "Closed"
            ? `<div class="wa-empty">${__("This chat is closed because the customer service window expired. Send an approved template to start a new WhatsApp conversation.")}<br><button class="btn btn-primary wa-template-btn">${__("Send approved template")}</button></div>`
            : `<div class="chat-send">
    <div class="chat-actions">
        <button class="wa-attach" title="${__("Attach file")}" style="margin-right: -10px;">
            <svg viewBox="0 0 24 24" width="24" height="24" class=""><path fill="currentColor" d="M1.816 15.556v.002c0 1.502.584 2.912 1.646 3.972s2.472 1.647 3.974 1.647a5.58 5.58 0 0 0 3.972-1.645l9.547-9.548c.769-.768 1.147-1.767 1.058-2.817-.079-.968-.548-1.927-1.319-2.698-1.594-1.592-4.068-1.711-5.517-.262l-7.916 7.915c-.881.881-.792 2.25.214 3.261.959.958 2.423 1.053 3.263.215l5.511-5.512c.28-.28.267-.722.053-.936l-.244-.244c-.191-.191-.567-.349-.957.04l-5.506 5.506c-.18.18-.635.127-.976-.214-.098-.097-.576-.613-.213-.973l7.915-7.917c.818-.817 2.267-.699 3.23.262.5.501.802 1.1.849 1.685.051.573-.156 1.111-.589 1.543l-9.547 9.549a3.97 3.97 0 0 1-2.829 1.171 3.975 3.975 0 0 1-2.83-1.173 3.973 3.973 0 0 1-1.172-2.828c0-1.071.415-2.076 1.172-2.83l7.209-7.211c.157-.157.264-.579.028-.814L11.5 4.36a.57.57 0 0 0-.834.018l-7.205 7.207a5.577 5.577 0 0 0-1.645 3.971z"></path></svg>
        </button>
        <button class="wa-template-btn" title="${__("Send template")}">
            <svg viewBox="0 0 24 24" width="24" height="24" class=""><path fill="currentColor" d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM5 19V5h14v14H5zm2-6h10v2H7v-2zm0-4h10v2H7V9z"></path></svg>
        </button>
    </div>
    <input placeholder="${__("Type a message")}">
    <button class="btn btn-primary">${__("Send")}</button>
</div>`
        }`,
      );

    const tags = (conv.tags || "").split(",").map((t) => t.trim()).filter(Boolean);
    const optin = (conv.opt_in_status || "Unknown").toLowerCase().replace(" ", "-");
    const link_row = (label, doctype, value) =>
      value ? `<div class="wa-ctx-row"><span>${label}</span><a data-doctype="${doctype}" data-name="${esc(value)}">${esc(value)}</a></div>` : "";
    this.page.body
      .find(".wa-inbox section")
      .html(
        `<h3>${__("ERPNext Context")}</h3>
        <div class="wa-ctx-row"><span>${__("Phone")}</span><b>${esc(conv.phone_number)}</b></div>
        <div class="wa-ctx-row"><span>${__("Opt-in")}</span><b class="wa-optin ${esc(optin)}">${esc(conv.opt_in_status || "Unknown")}</b></div>
        <div class="wa-ctx-row"><span>${__("Assigned")}</span><b>${esc(conv.assigned_to || __("Unassigned"))}</b></div>
        ${link_row(__("Lead"), "Lead", conv.lead)}
        ${link_row(__("Customer"), "Customer", conv.customer)}
        ${link_row(__("Contact"), "Contact", conv.contact)}
        ${link_row(__("Issue"), "Issue", conv.issue)}
        ${tags.length ? `<div class="wa-ctx-row"><span>${__("Tags")}</span><div class="wa-tags">${tags.map((t) => `<span class="wa-tag">${esc(t)}</span>`).join("")}</div></div>` : ""}
        ${conv.sla_breached ? `<div class="wa-ctx-alert">${__("SLA breached")}</div>` : ""}
        <button class="btn btn-sm btn-default wa-issue">${conv.issue ? __("Open Issue") : __("Create Issue")}</button>`,
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
    this.page.body.find(".chat-send input").on("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.page.body.find(".chat-send > button").trigger("click");
      }
    });
    this.page.body.find(".wa-img").on("click", (e) => window.open($(e.currentTarget).data("open"), "_blank"));
    this.page.body.find(".wa-template-btn").on("click", () => {
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

    this.page.body.find(".wa-assign").on("click", () => {
      let dialog = new frappe.ui.Dialog({
        title: __("Assign Conversation"),
        fields: [
          { label: __("User"), fieldname: "user", fieldtype: "Link", options: "User", reqd: 1, default: conv.assigned_to },
        ],
        primary_action_label: __("Assign"),
        primary_action: async (values) => {
          dialog.hide();
          await frappe.call("frappe_whatsapp.frappe_whatsapp.api.command_center.assign_conversation", {
            conversation: name,
            user: values.user,
          });
          await this.load();
          this.goto_conversation(name);
        },
      });
      dialog.show();
    });
    this.page.body.find(".wa-status-select").on("change", async (e) => {
      await frappe.call("frappe_whatsapp.frappe_whatsapp.api.command_center.update_conversation", {
        conversation: name,
        status: e.target.value,
      });
      await this.load();
      this.goto_conversation(name);
    });
    this.page.body.find(".wa-priority-select").on("change", async (e) => {
      await frappe.call("frappe_whatsapp.frappe_whatsapp.api.command_center.update_conversation", {
        conversation: name,
        priority: e.target.value,
      });
      await this.load();
      this.goto_conversation(name);
    });
    this.page.body.find(".wa-ctx-row a[data-doctype]").on("click", (e) => {
      e.preventDefault();
      frappe.set_route("Form", $(e.currentTarget).data("doctype"), $(e.currentTarget).data("name"));
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
