from __future__ import annotations

import hashlib
import hmac
import re
from typing import Iterable

import frappe
from frappe import _

PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")


def normalize_phone(value: str | None) -> str:
    phone = re.sub(r"[^0-9+]", "", value or "")
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not PHONE_RE.match(phone):
        frappe.throw(_("Invalid WhatsApp phone number"))
    return phone.lstrip("+")


def require_roles(roles: Iterable[str]) -> None:
    frappe.only_for(tuple(roles))


def get_raw_body() -> bytes:
    data = frappe.request.get_data(cache=True) if frappe.request else b""
    return data or b""


def verify_meta_signature(app_secret: str, raw_body: bytes | None = None) -> bool:
    if not app_secret or not frappe.request:
        return False
    signature = frappe.request.headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        return False
    supplied = signature.split("=", 1)[1]
    expected = hmac.new(app_secret.encode("utf-8"), raw_body or get_raw_body(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def assert_meta_signature(account, raw_body: bytes | None = None) -> None:
    secret = account.get_password("app_secret", raise_exception=False)
    if not secret:
        frappe.throw(_("Meta App Secret is not configured for WhatsApp Account {0}").format(account.name), frappe.AuthenticationError)
    if not verify_meta_signature(secret, raw_body):
        frappe.throw(_("Invalid Meta webhook signature"), frappe.AuthenticationError)
