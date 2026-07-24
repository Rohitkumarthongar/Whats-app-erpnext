"""Secure Meta WhatsApp webhook implementation for Frappe v16."""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime
from werkzeug.wrappers import Response

from frappe_whatsapp.utils import get_whatsapp_account
from frappe_whatsapp.utils.security import assert_meta_signature, get_raw_body

STATUS_RANK = {"queued": 0, "accepted": 1, "sent": 2, "delivered": 3, "read": 4, "failed": 99, "deleted": 100}
MEDIA_TYPES = {"image", "audio", "video", "document"}
MAX_MEDIA_BYTES = 25 * 1024 * 1024


@frappe.whitelist(allow_guest=True)
def webhook():
    if frappe.request.method == "GET":
        return verify_webhook()
    if frappe.request.method != "POST":
        frappe.throw(_("Method not allowed"))
    return process_webhook()


def verify_webhook():
    challenge = frappe.form_dict.get("hub.challenge")
    token = frappe.form_dict.get("hub.verify_token")
    mode = frappe.form_dict.get("hub.mode")
    if mode != "subscribe" or not token:
        return Response("Invalid verification request", status=400)
    if not frappe.db.exists("WhatsApp Account", {"webhook_verify_token": token, "status": "Active"}):
        return Response("Verification failed", status=403)
    return Response(challenge or "", status=200)


def process_webhook():
    raw = get_raw_body()
    data = frappe.request.get_json(silent=True) or {}
    changes = [change for entry in data.get("entry", []) for change in entry.get("changes", [])]
    if not changes:
        return Response("EVENT_RECEIVED", status=200)

    # Resolve account before accepting the payload. Message callbacks carry phone_number_id;
    # template callbacks may carry business account id, so both are supported.
    value = changes[0].get("value") or {}
    phone_id = (value.get("metadata") or {}).get("phone_number_id")
    business_id = data.get("entry", [{}])[0].get("id")
    account = get_whatsapp_account(phone_id) if phone_id else None
    if not account and business_id:
        name = frappe.db.get_value("WhatsApp Account", {"business_id": business_id, "status": "Active"}, "name")
        account = frappe.get_doc("WhatsApp Account", name) if name else None
    if not account:
        frappe.throw(_("Unable to resolve WhatsApp Account"), frappe.AuthenticationError)
    assert_meta_signature(account, raw)

    _log_payload(data, account.name)
    for change in changes:
        field = change.get("field")
        value = change.get("value") or {}
        if field == "messages":
            for message in value.get("messages") or []:
                _ingest_message(message, value, account)
            for status in value.get("statuses") or []:
                _update_message_status(status)
        elif field == "message_template_status_update":
            _update_template_status(value, account.name)
    return Response("EVENT_RECEIVED", status=200)


def _log_payload(data, account):
    frappe.get_doc({"doctype": "WhatsApp Notification Log", "template": "Webhook", "meta_data": json.dumps(data, ensure_ascii=False), "whatsapp_account": account if frappe.get_meta("WhatsApp Notification Log").has_field("whatsapp_account") else None}).insert(ignore_permissions=True)


def _ingest_message(message, value, account):
    message_id = message.get("id")
    if not message_id or frappe.db.exists("WhatsApp Message", {"message_id": message_id}):
        return
    contacts = value.get("contacts") or []
    profile = ((contacts[0].get("profile") or {}).get("name") if contacts else None)
    msg_type = message.get("type") or "text"
    context = message.get("context") or {}
    fields = {
        "doctype": "WhatsApp Message", "type": "Incoming", "from": message.get("from"),
        "message_id": message_id, "reply_to_message_id": context.get("id"),
        "is_reply": int(bool(context.get("id") and not context.get("forwarded"))),
        "content_type": msg_type if msg_type in {"text","document","image","video","audio","flow","reaction","location","contact","button","interactive","order"} else "text",
        "profile_name": profile, "whatsapp_account": account.name,
    }
    if msg_type == "text":
        fields["message"] = (message.get("text") or {}).get("body")
    elif msg_type == "reaction":
        reaction = message.get("reaction") or {}; fields.update(message=reaction.get("emoji"), reply_to_message_id=reaction.get("message_id"), content_type="reaction")
    elif msg_type == "button":
        fields["message"] = (message.get("button") or {}).get("text")
    elif msg_type == "interactive":
        interactive = message.get("interactive") or {}; kind = interactive.get("type")
        payload = interactive.get(kind) or {}
        if kind == "nfm_reply":
            response = _safe_json(payload.get("response_json")); fields.update(content_type="flow", flow_response=json.dumps(response), message=_summary(response))
        else:
            fields.update(content_type="button", message=payload.get("id") or payload.get("title"))
    elif msg_type == "order":
        fields.update(message=_("New Order Received via WhatsApp"), product_catalog_json=json.dumps(message.get("order") or {}))
    elif msg_type in MEDIA_TYPES:
        media = message.get(msg_type) or {}; fields["message"] = media.get("caption") or ""
        doc = frappe.get_doc(fields).insert(ignore_permissions=True)
        _download_media(doc, media.get("id"), account, msg_type)
        return
    else:
        fields["message"] = json.dumps(message.get(msg_type) or {}, ensure_ascii=False)
    frappe.get_doc(fields).insert(ignore_permissions=True)


def _download_media(message_doc, media_id, account, media_type):
    if not media_id:
        return
    timeout = account.request_timeout or 30
    headers = {"Authorization": "Bearer " + account.get_password("token")}
    base = f"{account.url.rstrip('/')}/{account.version}"
    meta = requests.get(f"{base}/{media_id}", headers=headers, timeout=timeout)
    meta.raise_for_status(); info = meta.json()
    response = requests.get(info["url"], headers=headers, timeout=timeout, stream=True)
    response.raise_for_status()
    size = int(response.headers.get("Content-Length") or 0)
    if size and size > MAX_MEDIA_BYTES:
        frappe.throw(_("Media exceeds the 25 MB limit"))
    content = response.content
    if len(content) > MAX_MEDIA_BYTES:
        frappe.throw(_("Media exceeds the 25 MB limit"))
    mime = (info.get("mime_type") or response.headers.get("Content-Type") or "application/octet-stream").split(";")[0]
    extension = mimetypes.guess_extension(mime) or Path((message_doc.message or "file")).suffix or ".bin"
    file_doc = frappe.get_doc({"doctype": "File", "file_name": f"{frappe.generate_hash(length=16)}{extension}", "attached_to_doctype": "WhatsApp Message", "attached_to_name": message_doc.name, "attached_to_field": "attach", "content": content, "is_private": 1}).save(ignore_permissions=True)
    frappe.db.set_value("WhatsApp Message", message_doc.name, "attach", file_doc.file_url, update_modified=False)


def _update_template_status(data, account):
    template_id = data.get("message_template_id")
    if template_id:
        frappe.db.set_value("WhatsApp Templates", {"id": template_id, "whatsapp_account": account}, "status", data.get("event"), update_modified=False)


def _update_message_status(status):
    message_id = status.get("id")
    name = frappe.db.get_value("WhatsApp Message", {"message_id": message_id}, "name")
    if not name:
        return
    doc = frappe.get_doc("WhatsApp Message", name)
    new_status = status.get("status") or ""
    current = (doc.status or "").lower()
    if current and STATUS_RANK.get(new_status, -1) < STATUS_RANK.get(current, -1) and new_status != "failed":
        return
    doc.status = new_status
    doc.status_updated_at = now_datetime()
    doc.conversation_id = (status.get("conversation") or {}).get("id") or doc.conversation_id
    errors = status.get("errors") or []
    doc.failure_reason = json.dumps(errors, ensure_ascii=False) if errors else None
    doc.save(ignore_permissions=True)


def _safe_json(value):
    try: return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError): return {}


def _summary(data):
    return ", ".join(f"{k}: {v}" for k, v in data.items() if v not in (None, "", [], {})) or "Flow completed"

# Backward-compatible names used by existing tests/integrations.
get = verify_webhook
post = process_webhook
update_message_status = lambda data: [_update_message_status(s) for s in (data.get("statuses") or [])]
update_template_status = lambda data: _update_template_status(data, data.get("whatsapp_account"))
