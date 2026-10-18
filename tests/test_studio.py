import unittest
from pathlib import Path
from unittest import mock

import studio
from bot import handle_update
from config import Config

CFG = Config("t", "g", frozenset({1}))


class FakeTg:
    def __init__(self):
        self.sent, self.edits, self.answers = [], [], []

    def send_message(self, chat_id, text, reply_markup=None, reply_to=None, entities=None):
        self.sent.append((chat_id, text, reply_markup, reply_to, entities))
        return 5

    def edit_message(self, chat_id, mid, text, reply_markup=None, entities=None):
        self.edits.append((chat_id, mid, text, entities))

    def answer_callback(self, cid, text=""):
        self.answers.append(cid)


def video(caption):
    return {"update_id": 1, "message": {"message_id": 7, "chat": {"id": 1}, "caption": caption,
                                        "video": {"file_id": "FID", "file_size": 100}}}


class TriggerTests(unittest.TestCase):
    def test_caption_text_and_links(self):
        self.assertEqual(studio.render_text({"caption": "رندر\nسلام دنیا"}), "سلام دنیا")
        self.assertEqual(studio.render_text({"text": "رندر https://drive.google.com/file/d/AbC_1/view سلام"}), "سلام")
        self.assertIsNone(studio.render_text({"caption": "words x"}))

    def test_parse_roundtrip_and_the_visible_text_is_only_the_question(self):
        st = {"template": "yaran", "name": "علی", "text": "یک  دو\nسه", "ref": "FID"}
        text, ents = studio.build(studio.ASK_TITLE, st)
        self.assertEqual(text, "🎬 " + studio.ASK_TITLE)
        got = studio.parse({"text": text, "entities": ents})
        self.assertEqual(got, {"template": "yaran", "name": "علی", "text": "یک دو سه", "ref": "FID"})
        self.assertIsNone(studio.parse({"text": "سلام"}))

    def test_a_too_long_state_stays_visible_in_the_text(self):
        import os
        text, ents = studio.build(studio.ASK_NAME, {"text": os.urandom(2000).hex(), "ref": "FID"})
        self.assertIsNone(ents)
        self.assertEqual(studio.parse({"text": text})["ref"], "FID")


class FlowTests(unittest.TestCase):
    def test_video_asks_the_template(self):
        tg = FakeTg()
        handle_update(video("رندر متن برش"), CFG, tg, None)
        chat, text, markup, reply_to, ents = tg.sent[0]
        self.assertEqual(reply_to, 7)
        self.assertEqual(text, "🎬 " + studio.ASK_TEMPLATE)
        self.assertEqual(studio.parse({"text": text, "entities": ents}), {"text": "متن برش", "ref": "FID"})
        self.assertEqual([b["callback_data"] for b in markup["inline_keyboard"][0]], ["tp:gap", "tp:yaran"])

    def test_empty_text_is_asked_for(self):
        tg = FakeTg()
        handle_update(video("رندر"), CFG, tg, None)
        self.assertEqual(tg.sent[0][1], studio.NEED_TEXT)

    def test_reply_to_a_suggestion_takes_its_speech(self):
        tg = FakeTg()
        upd = video("رندر")
        upd["message"]["reply_to_message"] = {"text": "🎬 برش 1\n0:10.0 – 0:50.0 (40ث)\n\n«سلام  دنیا\nخوبی»\n\nچرا: x"}
        handle_update(upd, CFG, tg, None)
        self.assertEqual(studio.parse({"text": tg.sent[0][1], "entities": tg.sent[0][4]})["text"], "سلام دنیا خوبی")

    def test_button_then_name_then_title_renders(self):
        tg = FakeTg()
        base = {"text": "متن برش", "ref": "FID"}
        body, ents = studio.build(studio.ASK_TEMPLATE, base)
        cb = {"update_id": 2, "callback_query": {"id": "c", "data": "tp:gap", "message": {
            "message_id": 9, "chat": {"id": 1}, "text": body, "entities": ents}}}
        handle_update(cb, CFG, tg, None)
        self.assertEqual(tg.edits[0][2], "🎬 " + studio.ASK_NAME)
        made = []
        name = {"update_id": 3, "message": {"message_id": 10, "chat": {"id": 1}, "text": "علی رضایی",
                                            "reply_to_message": {"text": tg.edits[0][2], "entities": tg.edits[0][3]}}}
        handle_update(name, CFG, tg, None, make=lambda c, s: made.append(s))
        self.assertEqual(tg.sent[-1][1], "🎬 " + studio.ASK_TITLE)
        self.assertEqual(made, [])
        title = {"update_id": 4, "message": {"message_id": 11, "chat": {"id": 1}, "text": "استاد دانشگاه",
                                             "reply_to_message": {"text": tg.sent[-1][1], "entities": tg.sent[-1][4]}}}
        handle_update(title, CFG, tg, None, make=lambda c, s: made.append(s))
        self.assertEqual(tg.sent[-1][1], "🎬 " + studio.ASK_MUSIC)  # the title is not the last question any more
        self.assertEqual([b["callback_data"] for b in tg.sent[-1][2]["inline_keyboard"][0]], ["mu:1", "mu:0"])
        self.assertEqual(made, [])
        press = {"update_id": 5, "callback_query": {"id": "m", "data": "mu:1", "message": {
            "message_id": 12, "chat": {"id": 1}, "text": tg.sent[-1][1], "entities": tg.sent[-1][4]}}}
        handle_update(press, CFG, tg, None, make=lambda c, s: made.append(s))
        self.assertEqual(made, [{"template": "gap", "name": "علی رضایی", "text": "متن برش", "ref": "FID",
                                 "title": "استاد دانشگاه", "music": "yes"}])

    def test_old_visible_state_messages_still_work(self):
        old = "🎬 حالا عنوان مهمان؟\nقالب: یاران خراسانی\nنام: علی\nمتن: سلام\nref: FID"
        self.assertEqual(studio.parse({"text": old}), {"template": "yaran", "name": "علی", "text": "سلام", "ref": "FID"})

    def test_unrelated_reply_is_not_ours(self):
        tg = FakeTg()
        msg = {"update_id": 5, "message": {"message_id": 1, "chat": {"id": 1}, "text": "hi",
                                           "reply_to_message": {"text": "something else"}}}
        handle_update(msg, CFG, tg, None, make=lambda c, s: self.fail("rendered"))


class MusicTests(unittest.TestCase):
    def test_channel_track_with_the_mood_is_preferred(self):
        tg = mock.Mock()
        tg.get_file_path.return_value = "p.mp3"
        tg.download.side_effect = lambda p, d: Path(d).write_bytes(b"x")
        rows = [{"file_id": "A", "tags": ["غمگین"]}, {"file_id": "B", "tags": ["حماسی"]}]
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f, l = studio.pick_music("غمگین", rows, tg, Path(d), lambda p: -14.0)
        self.assertTrue(f.endswith("music_in.mp3"))
        tg.get_file_path.assert_called_once_with("A")

    def test_no_mood_match_uses_any_channel_track(self):
        tg = mock.Mock()
        tg.get_file_path.return_value = "p.mp3"
        tg.download.side_effect = lambda p, d: Path(d).write_bytes(b"x")
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f, l = studio.pick_music("حماسی", [{"file_id": "Z", "tags": ["غمگین"]}], tg, Path(d), lambda p: -20.0)
        self.assertTrue(f.endswith("music_in.mp3"))
        self.assertEqual(l, -20.0)

    def test_empty_catalog_means_no_music_never_synthesized(self):
        self.assertEqual(studio.pick_music("حماسی", [], mock.Mock(), Path("."), lambda p: -20.0), (None, None))

    def test_bundled_url_track_is_fetched_by_mood(self):
        import tempfile
        got = []
        def fetch(url, dest):
            got.append(url)
            Path(dest).write_bytes(b"x")
        rows = [{"url": "http://a/x.mp3", "tags": ["غمگین"]}, {"url": "http://a/y.mp3", "tags": ["حماسی"]}]
        with tempfile.TemporaryDirectory() as d:
            f, l = studio.pick_music("حماسی", rows, None, Path(d), lambda p: -18.0, fetch=fetch)
        self.assertEqual(got, ["http://a/y.mp3"])
        self.assertTrue(f.endswith("music_in.mp3"))

    def test_bundled_library_is_tagged_with_known_moods(self):
        import music_bundled
        self.assertGreaterEqual(len(music_bundled.ROWS), 10)
        for r in music_bundled.ROWS:
            self.assertTrue(r["url"].startswith("https://raw.githubusercontent.com/"))
            self.assertTrue(set(r["tags"]) <= set(studio.MOODS), r)

    def test_failing_download_means_no_music(self):
        tg = mock.Mock()
        tg.get_file_path.side_effect = RuntimeError("x")
        self.assertEqual(studio.pick_music("x", [{"file_id": "A"}], tg, Path("."), lambda p: 0.0), (None, None))

    def test_unknown_mood_falls_back(self):
        c = mock.Mock()
        c.generate_json.return_value = [{"mood": "نامعلوم"}]
        self.assertEqual(studio.choose_mood(c, "x"), studio.DEFAULT_MOOD)
        c.generate_json.side_effect = RuntimeError
        self.assertEqual(studio.choose_mood(c, "x"), studio.DEFAULT_MOOD)


if __name__ == "__main__":
    unittest.main()


CLIP_MSG = ("🎬 برش 2\n12:30.0 – 13:35.0 (65ث)\n\n«این متن همان برش است»\n\nچرا: دلیل")


def press_make():
    return {"update_id": 3, "callback_query": {"id": "cb", "data": "mk", "message": {
        "message_id": 9, "chat": {"id": 1}, "text": CLIP_MSG}}}


class MakeButtonTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.pending = Path(self.d.name) / "memory" / "pending.json"

    def test_button_asks_for_the_video_with_the_time_range(self):
        tg = FakeTg()
        handle_update(press_make(), CFG, tg, lambda *a: None, pending_path=self.pending)
        self.assertIn("12:30.0", tg.sent[0][1])
        self.assertIn("13:35.0", tg.sent[0][1])
        self.assertEqual(tg.answers, ["cb"])

    def test_next_video_starts_the_template_question_with_the_clip_text(self):
        tg = FakeTg()
        handle_update(press_make(), CFG, tg, lambda *a: None, pending_path=self.pending)
        tg.sent.clear()
        v = {"update_id": 4, "message": {"message_id": 11, "chat": {"id": 1},
                                         "video": {"file_id": "FID", "file_size": 100, "duration": 66}}}
        handle_update(v, CFG, tg, lambda *a: None, pending_path=self.pending)
        self.assertEqual(tg.sent[0][1].split(" ", 1)[1], studio.ASK_TEMPLATE)
        st = studio.parse({"text": tg.sent[0][1], "entities": tg.sent[0][4]})
        self.assertEqual((st["text"], st["ref"]), ("این متن همان برش است", "FID"))

    def test_the_wait_is_used_once(self):
        tg = FakeTg()
        handle_update(press_make(), CFG, tg, lambda *a: None, pending_path=self.pending)
        msg = {"message_id": 11, "chat": {"id": 1}, "video": {"file_id": "F", "file_size": 1, "duration": 60}}
        self.assertIsNotNone(studio.take_pending(self.pending, msg))
        self.assertIsNone(studio.take_pending(self.pending, msg))

    def test_a_whole_interview_is_not_taken_for_the_clip(self):
        tg = FakeTg()
        handle_update(press_make(), CFG, tg, lambda *a: None, pending_path=self.pending)
        msg = {"message_id": 11, "chat": {"id": 1}, "video": {"file_id": "F", "file_size": 1, "duration": 3000}}
        self.assertIsNone(studio.take_pending(self.pending, msg))
        self.assertIsNotNone(studio.take_pending(self.pending, {**msg, "video": {**msg["video"], "duration": 70}}))

    def test_plain_text_never_consumes_the_wait(self):
        tg = FakeTg()
        handle_update(press_make(), CFG, tg, lambda *a: None, pending_path=self.pending)
        self.assertIsNone(studio.take_pending(self.pending, {"chat": {"id": 1}, "text": "سلام"}))


class NoReplyNeededTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.asks = Path(self.d.name) / "memory" / "asks.json"
        self.tg = FakeTg()
        self.made = []
        body, ents = studio.build(studio.ASK_TEMPLATE, {"text": "متن برش", "ref": "FID"})
        cb = {"update_id": 2, "callback_query": {"id": "c", "data": "tp:gap", "message": {
            "message_id": 9, "chat": {"id": 1}, "text": body, "entities": ents}}}
        handle_update(cb, CFG, self.tg, None, ask_path=self.asks)

    def say(self, text, uid=3, **extra):
        msg = {"message_id": uid, "chat": {"id": 1}, "text": text, **extra}
        handle_update({"update_id": uid, "message": msg}, CFG, self.tg, None,
                      make=lambda c, s: self.made.append(s), ask_path=self.asks)

    def test_name_and_title_work_without_any_reply(self):
        self.say("میلاد تاجیک")
        self.assertEqual(self.tg.sent[-1][1], "🎬 " + studio.ASK_TITLE)
        self.assertEqual(self.made, [])
        self.say("سرآشپز افغانستانی", uid=4)
        self.assertEqual(self.tg.sent[-1][1], "🎬 " + studio.ASK_MUSIC)
        self.assertEqual(self.made, [])  # the video is made only after the music answer

    def test_the_answer_is_used_once(self):
        self.say("میلاد تاجیک")
        self.say("سرآشپز", uid=4)
        sent = len(self.tg.sent)
        self.say("سلام", uid=5)
        self.assertEqual(self.made, [])  # not taken as another answer; only the music button renders
        self.assertGreater(len(self.tg.sent), sent)  # an ordinary message gets the usual answer again

    def test_links_and_render_captions_are_not_taken_for_an_answer(self):
        self.say("https://drive.google.com/file/d/AbC_1/view")
        self.say("رندر متن")
        self.assertEqual(self.made, [])
        self.assertNotEqual(self.tg.sent[-1][1], "🎬 " + studio.ASK_TITLE)

    def test_an_old_question_expires(self):
        import json
        data = json.loads(self.asks.read_text(encoding="utf-8"))
        for v in data.values():
            v["at"] -= studio.PENDING_TTL + 5
        self.asks.write_text(json.dumps(data), encoding="utf-8")
        before = len(self.tg.sent)
        self.say("میلاد تاجیک")
        self.assertEqual(self.made, [])
        self.assertTrue(all(m[1] != "🎬 " + studio.ASK_TITLE for m in self.tg.sent[before:]))


class MusicChoiceTests(unittest.TestCase):
    ST = {"template": "gap", "name": "علی", "title": "مدیر", "text": "متن برش", "ref": "FID"}

    def press(self, data, st=None, chat=1):
        tg, made = FakeTg(), []
        body, ents = studio.build(studio.ASK_MUSIC, self.ST if st is None else st)
        cb = {"update_id": 2, "callback_query": {"id": "m", "data": data, "message": {
            "message_id": 9, "chat": {"id": chat}, "text": body, "entities": ents}}}
        handle_update(cb, CFG, tg, None, make=lambda c, s: made.append(s))
        return tg, made

    def test_yes_renders_with_music(self):
        tg, made = self.press("mu:1")
        self.assertEqual(made[0]["music"], "yes")
        self.assertEqual(made[0]["title"], "مدیر")
        self.assertEqual(tg.edits[0][2], "🎬 " + studio.MUSIC_LABELS["yes"])

    def test_no_renders_without_music(self):
        tg, made = self.press("mu:0")
        self.assertEqual(made[0]["music"], "no")

    def test_a_stranger_chat_or_an_unfinished_state_renders_nothing(self):
        self.assertEqual(self.press("mu:1", chat=99)[1], [])
        self.assertEqual(self.press("mu:1", st={"text": "متن", "ref": "FID"})[1], [])

    def test_music_answer_survives_the_long_state_fallback(self):
        import os
        st = {**self.ST, "music": "no", "text": os.urandom(2000).hex()}
        text, ents = studio.build(studio.ASK_MUSIC, st)
        self.assertIsNone(ents)
        got = studio.parse({"text": text})
        self.assertEqual((got["title"], got["music"], got["template"]), ("مدیر", "no", "gap"))


class MakeVideoMusicTests(unittest.TestCase):
    def run_make(self, music):
        from unittest import mock
        import sys
        import types
        calls = {}
        fake_render = types.SimpleNamespace(
            lufs_of=lambda f: -14.0,
            main=lambda *a, **k: calls.update(music_file=k.get("music_file"), music_lufs=k.get("music_lufs")))
        tg = FakeTg()
        tg.send_video = lambda *a, **k: calls.update(caption=k.get("caption"))
        picked = []
        st = {"template": "gap", "name": "علی", "title": "مدیر", "text": "من به خانه رفتم", "ref": "FID"}
        if music:
            st["music"] = music
        import tempfile
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(sys.modules, {"gap_render": fake_render}), \
                mock.patch.object(studio, "fetch_input", lambda *a, **k: Path(d) / "v.mp4"), \
                mock.patch.object(studio, "to_audio", lambda *a, **k: Path(d) / "a.mp3"), \
                mock.patch.object(studio, "perfect_text", lambda c, a, t: t), \
                mock.patch.object(studio, "fix_text", lambda c, t: t), \
                mock.patch.object(studio, "choose_mood", lambda c, t: picked.append("mood") or "حماسی"), \
                mock.patch.object(studio, "pick_music",
                                  lambda *a, **k: picked.append("pick") or ("track.mp3", -12.0)):
            (Path(d) / "debug").mkdir()
            align = types.SimpleNamespace(align_words=lambda audio, text: [
                {"text": w, "heard": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate(text.split())])
            studio.make_video(1, st, tg, align, object(), Path(d), Path(d) / "m" / "catalog.json")
        return calls, picked

    def test_default_and_yes_use_the_music_library(self):
        for music in (None, "yes"):
            calls, picked = self.run_make(music)
            self.assertEqual(picked, ["mood", "pick"])
            self.assertEqual(calls["music_file"], "track.mp3")
            self.assertIn("حال‌وهوا", calls["caption"])

    def test_no_means_no_music_at_all(self):
        calls, picked = self.run_make("no")
        self.assertEqual(picked, [])
        self.assertIsNone(calls["music_file"])
        self.assertNotIn("حال‌وهوا", calls["caption"])


class FixTextTests(unittest.TestCase):
    class Client:
        def __init__(self, out):
            self.out = out

        def generate_json(self, prompt):
            if isinstance(self.out, Exception):
                raise self.out
            return [{"text": self.out}]

    def test_obvious_misheard_words_are_fixed(self):
        text = "و اصلاً هیچی اصلاً نمیذاره خوفی و فکرهایی که ول کنه خود خو و شما را"
        fixed = studio.fix_text(self.Client("و اصلاً هیچی اصلاً نمیذاره خوشی و فکرهایی که ول کنه خودتو و شما را"), text)
        self.assertEqual(fixed, "و اصلاً هیچی اصلاً نمیذاره خوشی و فکرهایی که ول کنه خودتو و شما را")

    def test_a_rewritten_text_is_rejected(self):
        text = "این یک جمله ی معمولی است که باید همین طور بماند"
        self.assertEqual(studio.fix_text(self.Client("متنی کاملاً متفاوت و بازنویسی شده توسط مدل زبانی"), text), text)

    def test_a_failing_client_keeps_the_text(self):
        self.assertEqual(studio.fix_text(self.Client(RuntimeError("x")), "سلام دنیا"), "سلام دنیا")

    def test_added_words_are_ignored(self):
        self.assertEqual(studio.fix_text(self.Client("سلام خیلی دنیا"), "سلام دنیا"), "سلام دنیا")
