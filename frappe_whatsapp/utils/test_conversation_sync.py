"""DB-free tests for how an incoming WhatsApp reply is filed and survives a bookkeeping failure.

Background: ``WhatsApp Conversation.phone_number`` is unique. Once a conversation was
closed (24 h after the contact's last reply) the next message from that contact tried to
insert a second row, raised a duplicate-key error, and - being raised inside the
``after_insert`` hook - rolled back the whole webhook request. The reply vanished without
a trace and the Approve / Reject handler never ran.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from frappe_whatsapp.utils import conversation as conv_mod
from frappe_whatsapp.utils import webhook as webhook_mod
from frappe_whatsapp.utils.conversation import pick_conversation


def row(name, phone, status="Open"):
    return {"name": name, "phone_number": phone, "status": status}


class TestPickConversation(unittest.TestCase):
    def test_exact_number_wins_even_when_closed(self):
        rows = [row("a", "918233189764", "Closed"), row("b", "8233189764", "Open")]
        self.assertEqual(pick_conversation(rows, "918233189764")["name"], "a")

    def test_closed_exact_match_is_returned_not_ignored(self):
        # the old code skipped closed rows, then tried to insert a duplicate of this one
        self.assertEqual(pick_conversation([row("k", "919878507000", "Closed")], "919878507000")["name"], "k")

    def test_same_contact_without_country_code_is_matched(self):
        self.assertEqual(pick_conversation([row("a", "8233189764")], "918233189764")["name"], "a")

    def test_open_beats_closed_for_a_suffix_match(self):
        rows = [row("closed", "8233189764", "Closed"), row("open", "08233189764", "Open")]
        self.assertEqual(pick_conversation(rows, "918233189764")["name"], "open")

    def test_no_match(self):
        self.assertIsNone(pick_conversation([row("a", "919999999999")], "918233189764"))
        self.assertIsNone(pick_conversation([], "918233189764"))

    def test_short_numbers_only_match_exactly(self):
        self.assertIsNone(pick_conversation([row("a", "9123456")], "123456"))
        self.assertEqual(pick_conversation([row("a", "123456")], "123456")["name"], "a")


class FakeMessage(dict):
    """Just enough of a WhatsApp Message document for the sync hook."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.__dict__.update(kw)

    def get(self, key, default=None):
        return dict.get(self, key, default)


class FakeConversation:
    def __init__(self, name, phone, status):
        self.name, self.phone_number, self.status = name, phone, status
        self.closed_at = "2026-10-27 19:02:40" if status == "Closed" else None
        self.opened_at = "2026-10-26 12:42:32"
        self.unread_count = 0
        self.saved = False

    def save(self, **kwargs):
        self.saved = True


def incoming(phone="919878507000"):
    return FakeMessage(
        doctype="WhatsApp Message", name="m1", type="Incoming", content_type="button", message="Approve",
        whatsapp_account="Mel Platform", template=None, creation="2026-11-24 12:40:00", to=None,
        **{"from": phone},
    )


class TestSyncReopensClosedConversation(unittest.TestCase):
    def run_sync(self, existing, doc, other_holder=False):
        conv = FakeConversation(*existing)
        with patch.object(frappe, "db", MagicMock()) as db, \
                patch.object(frappe, "get_doc", return_value=conv) as get_doc, \
                patch.object(conv_mod, "_find_conversation", return_value=row(*existing)), \
                patch.object(conv_mod, "now_datetime", return_value="2026-11-24 12:40:01"), \
                patch.object(conv_mod, "_handle_opt_out"):
            db.exists.return_value = other_holder
            conv_mod.sync_message_to_conversation(doc)
        return conv, get_doc

    def test_incoming_message_reopens_a_closed_conversation(self):
        conv, get_doc = self.run_sync(("k", "919878507000", "Closed"), incoming())
        self.assertEqual(conv.status, "Open")
        self.assertIsNone(conv.closed_at)
        self.assertTrue(conv.saved)
        # reopened, not duplicated: no new Conversation document was built
        for call in get_doc.call_args_list:
            self.assertNotIsInstance(call.args[0], dict, "a new conversation must not be created")

    def test_phone_number_is_not_moved_onto_a_number_another_conversation_holds(self):
        conv, _ = self.run_sync(("a", "8233189764", "Open"), incoming("918233189764"), other_holder=True)
        self.assertEqual(conv.phone_number, "8233189764")

    def test_phone_number_converges_when_it_is_free(self):
        conv, _ = self.run_sync(("a", "8233189764", "Open"), incoming("918233189764"), other_holder=False)
        self.assertEqual(conv.phone_number, "918233189764")

    def test_a_failure_while_filing_the_message_does_not_propagate(self):
        with patch.object(frappe, "db", MagicMock()) as db, \
                patch.object(frappe, "log_error") as log_error, \
                patch.object(conv_mod, "_sync_message_to_conversation", side_effect=RuntimeError("Duplicate entry")):
            conv_mod.sync_message_to_conversation(incoming())  # must not raise
        db.rollback.assert_called_once_with(save_point="whatsapp_conversation_sync")
        log_error.assert_called_once()


class TestWebhookStepIsGuarded(unittest.TestCase):
    def test_success_returns_the_value(self):
        with patch.object(frappe, "db", MagicMock()):
            self.assertEqual(webhook_mod._guarded("x", lambda a: a * 2, 21), 42)

    def test_failure_is_rolled_back_logged_and_swallowed(self):
        def boom():
            raise frappe.ValidationError("An active conversation already exists")

        with patch.object(frappe, "db", MagicMock()) as db, patch.object(frappe, "log_error") as log_error:
            self.assertIsNone(webhook_mod._guarded("incoming message wamid.X", boom))
        db.rollback.assert_called_once_with(save_point="whatsapp_webhook_step")
        self.assertIn("wamid.X", log_error.call_args.kwargs["message"])


if __name__ == "__main__":
    unittest.main()
