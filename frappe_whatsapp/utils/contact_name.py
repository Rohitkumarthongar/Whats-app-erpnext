import re

import frappe


def _last10(value):
    return re.sub(r"\D", "", value or "")[-10:]


def display_names(phones):
    """{phone: name} using the Employee name when the number is an employee's, else the WhatsApp Profile name."""
    wanted = {p: _last10(p) for p in phones if p}
    wanted = {p: k for p, k in wanted.items() if len(k) >= 7}
    if not wanted:
        return {}
    keys = set(wanted.values())

    by_key = {}
    for profile in frappe.get_all("WhatsApp Profiles", filters={"profile_name": ["is", "set"]}, fields=["number", "profile_name"]):
        if _last10(profile.number) in keys:
            by_key[_last10(profile.number)] = profile.profile_name
    # an employee's name wins over whatever name WhatsApp reports
    for emp in frappe.get_all("Employee", filters={"status": "Active", "cell_number": ["is", "set"]}, fields=["employee_name", "cell_number"]):
        if _last10(emp.cell_number) in keys and emp.employee_name:
            by_key[_last10(emp.cell_number)] = emp.employee_name
    return {p: by_key[k] for p, k in wanted.items() if k in by_key}


def display_name(phone):
    return display_names([phone]).get(phone)
