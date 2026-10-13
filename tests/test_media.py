import tempfile
import unittest
from pathlib import Path
from media import (InputError, InputRef, extract_drive_id, resolve_input,
                    fetch_input, to_audio)


class FakeTg:
    def __init__(self):
        self.calls = []

    def get_file_path(self, file_id):
        self.calls.append(("path", file_id))
        return "files/x.mp3"

    def download(self, file_path, dest):
        self.calls.append(("download", file_path))
        Path(dest).write_bytes(b"ID3audio")


class MediaTests(unittest.TestCase):
    def test_extract_drive_id_from_file_and_open_links(self):
        self.assertEqual(extract_drive_id(
            "https://drive.google.com/file/d/1AbC_-x/view?usp=sharing"), "1AbC_-x")
        self.assertEqual(extract_drive_id(
            "see https://drive.google.com/open?id=1AbC_-x ok"), "1AbC_-x")
        self.assertIsNone(extract_drive_id("hello"))

    def test_big_telegram_file_without_link_asks_for_drive(self):
        msg = {"audio": {"file_id": "f", "file_size": 26_000_000}}
        with self.assertRaises(InputError) as cm:
            resolve_input(msg)
        self.assertIn("۲۰ مگابایت", str(cm.exception))
        self.assertIn("Drive", str(cm.exception))

    def test_message_with_drive_link_resolves_to_drive(self):
        msg = {"text": "https://drive.google.com/file/d/1AbC_-x/view?usp=sharing"}
        self.assertEqual(resolve_input(msg), InputRef("drive", "1AbC_-x"))

    def test_big_file_with_drive_link_in_caption_uses_the_link(self):
        msg = {"video": {"file_id": "f", "file_size": 90_000_000},
               "caption": "https://drive.google.com/file/d/1AbC_-x/view"}
        self.assertEqual(resolve_input(msg).kind, "drive")

    def test_small_telegram_audio_resolves_to_telegram_file(self):
        msg = {"voice": {"file_id": "vv", "file_size": 3_000_000}}
        self.assertEqual(resolve_input(msg), InputRef("telegram", "vv"))

    def test_text_without_media_or_link_is_rejected(self):
        with self.assertRaises(InputError):
            resolve_input({"text": "سلام"})

    def test_private_drive_link_returning_html_is_reported(self):
        def html_downloader(url, output, quiet=True):
            Path(output).write_bytes(b"<!DOCTYPE html><html>sign in</html>")
            return output
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(InputError) as cm:
                fetch_input(InputRef("drive", "1AbC_-x"), FakeTg(), Path(d),
                            downloader=html_downloader)
        self.assertIn("Anyone with the link", str(cm.exception))

    def test_telegram_ref_is_downloaded_via_tg(self):
        tg = FakeTg()
        with tempfile.TemporaryDirectory() as d:
            p = fetch_input(InputRef("telegram", "vv"), tg, Path(d))
            self.assertTrue(p.exists())
        self.assertEqual(tg.calls[0], ("path", "vv"))

    def test_to_audio_on_non_media_raises_input_error(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "bad.mp3"
            src.write_bytes(b"not audio at all")
            with self.assertRaises(InputError):
                to_audio(src, Path(d) / "out.mp3")


if __name__ == "__main__":
    unittest.main()
