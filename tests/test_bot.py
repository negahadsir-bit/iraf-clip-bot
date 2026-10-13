import unittest
from config import Config
from bot import handle_update, RECEIVED

CFG = Config("t", "g", frozenset({1}))


class FakeTg:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def upd(chat=1, uid=10):
    return {"update_id": uid, "message": {"chat": {"id": chat}, "text": "hi"}}


class BotTests(unittest.TestCase):
    def test_unknown_chat_ignored_but_offset_advances(self):
        tg = FakeTg()
        nxt = handle_update(upd(chat=99), CFG, tg, lambda m: ["x"])
        self.assertEqual(tg.sent, [])
        self.assertEqual(nxt, 11)

    def test_allowed_gets_received_then_results(self):
        tg = FakeTg()
        nxt = handle_update(upd(), CFG, tg, lambda m: ["a", "b"])
        self.assertEqual([t for _, t in tg.sent], [RECEIVED, "a", "b"])
        self.assertEqual(nxt, 11)

    def test_offset_advanced_via_callback_after_received(self):
        tg, order = FakeTg(), []
        handle_update(upd(), CFG, tg, lambda m: order.append("process") or [],
                      commit=lambda o: order.append(("commit", o)))
        self.assertEqual(order, [("commit", 11), "process"])

    def test_update_without_message_is_skipped(self):
        tg = FakeTg()
        self.assertEqual(handle_update({"update_id": 5}, CFG, tg, lambda m: ["x"]), 6)
        self.assertEqual(tg.sent, [])


if __name__ == "__main__":
    unittest.main()
