# Copyright (c) 2026, Rohit Kumar Soni and contributors
from __future__ import annotations

import json
import frappe
from frappe import _
from frappe.utils import now_datetime

from frappe_whatsapp.utils.security import assert_meta_signature, get_raw_body


def _account_from_request(data: dict):
    account_name = data.get("whatsapp_account") or frappe.form_dict.get("whatsapp_account")
    if account_name:
        return frappe.get_doc("WhatsApp Account", account_name)
    active = frappe.get_all("WhatsApp Account", filters={"status": "Active"}, pluck="name", limit=2)
    if len(active) != 1:
        frappe.throw(_("Pass whatsapp_account when multiple active accounts exist"))
    return frappe.get_doc("WhatsApp Account", active[0])


@frappe.whitelist(allow_guest=True)
def handle_flow_request():
    """Secure WhatsApp Flow data endpoint for Frappe v16.

    Meta App Secret signature verification is mandatory. Flow payload data is
    persisted idempotently in WhatsApp Flow Data.
    """
    if frappe.request.method == "GET":
        return {"status": "ok"}

    raw_body = get_raw_body()
    data = frappe.request.get_json(silent=True) or {}
    if not data:
        frappe.throw(_("No data received"))

    account = _account_from_request(data)
    assert_meta_signature(account, raw_body)

    action = data.get("action")
    if action == "ping":
        return {"data": {"status": "active"}}
    if action == "INIT":
        return handle_init(account.name, data)
    if action == "data_exchange":
        return handle_data_exchange(account.name, data)
    if action == "BACK":
        return {"screen": data.get("screen"), "data": data.get("data") or {}}

    frappe.throw(_("Unsupported Flow action: {0}").format(action or "<empty>"))


def handle_init(account_name: str, data: dict):
    token = data.get("flow_token")
    if token:
        save_flow_data(token, data.get("screen"), data.get("data") or {}, account_name, "Started")
    return {"screen": data.get("screen") or "INIT", "data": data.get("data") or {}}


def handle_data_exchange(account_name: str, data: dict):
    token = data.get("flow_token")
    if not token:
        frappe.throw(_("flow_token is required"))
    form_data = data.get("data") or {}
    is_complete = bool(form_data.get("complete") or form_data.get("completed"))
    save_flow_data(token, data.get("screen"), form_data, account_name, "Completed" if is_complete else "In Progress")
    response = {"screen": data.get("screen"), "data": form_data}
    if is_complete:
        response["data"] = {"extension_message_response": {"params": {"flow_token": token}}}
    return response


def save_flow_data(flow_token: str, screen: str | None, form_data: dict, account_name: str, status: str):
    existing = frappe.db.exists("WhatsApp Flow Data", {"flow_token": flow_token})
    doc = frappe.get_doc("WhatsApp Flow Data", existing) if existing else frappe.new_doc("WhatsApp Flow Data")
    if not existing:
        doc.flow_token = flow_token
    current = json.loads(doc.data or "{}")
    current.update(form_data)
    doc.data = json.dumps(current, ensure_ascii=False)
    doc.last_screen = screen
    doc.whatsapp_account = account_name
    doc.status = status
    if status == "Completed":
        doc.completed_at = now_datetime()
    doc.save(ignore_permissions=True)
    return doc.name
