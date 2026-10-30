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
  { icon: "account", label: "Accounts", doctype: "WhatsApp Account" },
  { icon: "rules", label: "Automation Rules", doctype: "WhatsApp Automation Rule" },
  { icon: "campaigns", label: "Campaigns", doctype: "Bulk WhatsApp Message" },
  { icon: "consent", label: "Consent Log", doctype: "WhatsApp Consent" },
  { icon: "conversation", label: "Conversations", doctype: "WhatsApp Conversation" },
  { icon: "flow", label: "Flows", doctype: "WhatsApp Flow" },
  { icon: "message", label: "Messages", doctype: "WhatsApp Message" },
  { icon: "log", label: "Notification Log", doctype: "WhatsApp Notification Log" },
  { icon: "bell", label: "Notifications", doctype: "WhatsApp Notification" },
  { icon: "profiles", label: "Profiles", doctype: "WhatsApp Profiles" },
  { icon: "list", label: "Recipient Lists", doctype: "WhatsApp Recipient List" },
  { icon: "template", label: "Templates", doctype: "WhatsApp Templates" },
].sort((a, b) => a.label.localeCompare(b.label));
// Feather-style line icons (24x24 paths) for the side menu, so it stays usable when collapsed.
const NAV_ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
  inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  campaigns: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  automation: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  account: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  rules: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  consent: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
  conversation: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  flow: '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
  message: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.2A8.4 8.4 0 0 1 3.9 11.5 8.5 8.5 0 0 1 12.4 3 8.4 8.4 0 0 1 21 11.5z"/><line x1="8" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="13" y2="14"/>',
  log: '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  profiles: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  template: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
};
const nav_icon = (key) =>
  `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0" aria-hidden="true">${NAV_ICONS[key] || NAV_ICONS.list}</svg>`;
const nav_button = (attrs, label, icon) =>
  `<button ${attrs} title="${esc(label)}" aria-label="${esc(label)}"><span class="wa-nav-inner" style="display:flex;align-items:center;gap:12px">${nav_icon(icon)}<span class="wa-nav-label">${esc(label)}</span></span></button>`;
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
        <div class="wa-brand" role="button" tabindex="0" style="display:flex;align-items:center;gap:10px;padding:6px 18px 14px;cursor:pointer;user-select:none" title="${__("Collapse / expand menu")}">${this.brand_html()}<span class="wa-brand-name" style="font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(frappe.boot.sysdefaults?.company || "WhatsApp")}</span></div>
        ${nav_button('data-view="dashboard" class="active"', __("Dashboard"), "dashboard")}
        ${nav_button('data-view="inbox"', __("Inbox"), "inbox")}
        ${nav_button('data-view="campaigns" class="wa-nav-optional" data-flag="enable_campaigns"', __("Campaigns"), "campaigns")}
        ${nav_button('data-view="automation" class="wa-nav-optional" data-flag="enable_automation"', __("Automation"), "automation")}
        ${nav_button('data-view="settings"', __("Settings"), "settings")}
        ${MODULE_LINKS.map((m) =>
          nav_button(`class="wa-sidebar-link" data-doctype="${esc(m.doctype)}" ${m.single ? 'data-single="1"' : ""}`, __(m.label), m.icon),
        ).join("")}
      </nav>
      <div class="wa-main"><div class="wa-content"><div class="wa-loading">${__("Loading WhatsApp workspace...")}</div></div></div></div>`);
    this.set_collapsed(this.is_collapsed());
    this.page.body.on("click keydown", ".wa-brand", (e) => {
      if (e.type === "keydown" && !["Enter", " "].includes(e.key)) return;
      e.preventDefault();
      this.set_collapsed(!this.page.body.find(".wa-center").hasClass("wa-collapsed"));
    });
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
  brand_html() {
    const logo = frappe.boot.app_logo_url || (frappe.boot.website_settings || {}).app_logo;
    if (logo) return `<img class="wa-brand-logo" src="${esc(logo)}" alt="" style="width:32px;height:32px;max-width:32px;object-fit:contain;flex-shrink:0">`;
    const company = frappe.boot.sysdefaults?.company || "W";
    return `<span class="wa-brand-logo wa-brand-initial" style="width:32px;height:32px;display:grid;place-items:center;border-radius:8px;background:#128c7e;color:#fff;font-weight:700;flex-shrink:0">${esc(company[0].toUpperCase())}</span>`;
  }
  apply_optional_nav() {
    this.page.body.find(".wa-nav-optional").each((_, el) => {
      const flag = $(el).data("flag");
      $(el).toggle(!!((this.data || {}).settings || {})[flag]);
    });
  }
  is_collapsed() {
    try {
      return localStorage.getItem("wa_sidebar_collapsed") === "1";
    } catch (e) {
      return false;
    }
  }
  set_collapsed(collapsed) {
    this.page.body.find(".wa-center").toggleClass("wa-collapsed", !!collapsed);
    const $nav = this.page.body.find(".wa-sidebar");
    $nav.css({ width: collapsed ? "68px" : "", overflow: collapsed ? "hidden" : "" });
    // labels go, icons stay (each button keeps its tooltip); the logo is the toggle
    $nav.find(".wa-nav-label, .wa-brand-name").css("display", collapsed ? "none" : "");
    $nav.children("button").css("padding", collapsed ? "11px 0" : "");
    $nav.find(".wa-nav-inner").css("justify-content", collapsed ? "center" : "");
    $nav.children(".wa-brand").css({ padding: collapsed ? "6px 0 14px" : "6px 18px 14px", "justify-content": collapsed ? "center" : "" });
    try {
      localStorage.setItem("wa_sidebar_collapsed", collapsed ? "1" : "0");
    } catch (e) {}
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
    this.apply_optional_nav();
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
        const initial = (x.display_name || x.customer_name || x.phone_number || "?")[0].toUpperCase();
        const classes = ["wa-conv"];
        if (x.name === this.selected) classes.push("active");
        if (x.unread_count) classes.push("unread");
        return `<div class="${classes.join(" ")}" data-name="${esc(x.name)}">
          <div class="avatar" style="background:${this.avatar_color(x.display_name || x.customer_name || x.phone_number)}">${esc(initial)}</div>
          <div class="wa-conv-body">
            <div class="wa-conv-top"><b>${esc(x.display_name || x.customer_name || x.phone_number)}</b><span class="wa-conv-time">${this.relative_time(x.last_message_at)}</span></div>
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
        const hay = `${c.display_name || ""} ${c.customer_name || ""} ${c.phone_number || ""} ${c.last_message || ""}`.toLowerCase();
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

    const displayName = conv.display_name || conv.customer_name || conv.phone_number;
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
