import unittest
from unittest import mock

from frappe_whatsapp.utils import contact_name


def _fake_get_all(doctype, **kwargs):
    if doctype == "WhatsApp Profiles":
        return [{"number": "919878906000", "profile_name": "Karan"}, {"number": "911111111111", "profile_name": "Ajay"}]
    return [{"employee_name": "Karan Singh", "cell_number": "+91 98789 06000"}]


class TestContactName(unittest.TestCase):
    def test_employee_wins_then_profile_then_none(self):
        from frappe import _dict

        with mock.patch.object(contact_name.frappe, "get_all", side_effect=lambda d, **k: [_dict(r) for r in _fake_get_all(d)]):
            names = contact_name.display_names(["919878906000", "911111111111", "912222222222"])
        self.assertEqual(names, {"919878906000": "Karan Singh", "911111111111": "Ajay"})
