import unittest
from config import load_config, ConfigError


class ConfigTests(unittest.TestCase):
    def test_load_config_parses_ids(self):
        cfg = load_config({"BOT_TOKEN": "t", "GEMINI_API_KEY": "k",
                           "ALLOWED_CHAT_IDS": "6205566163, 94554237"})
        self.assertEqual(cfg.allowed_chat_ids, frozenset({6205566163, 94554237}))
        self.assertEqual(cfg.bot_token, "t")
        self.assertEqual(cfg.gemini_key, "k")

    def test_load_config_missing_key_raises_naming_only_the_variable(self):
        with self.assertRaises(ConfigError) as cm:
            load_config({"BOT_TOKEN": "secret-token", "ALLOWED_CHAT_IDS": "1"})
        msg = str(cm.exception)
        self.assertIn("GEMINI_API_KEY", msg)
        self.assertNotIn("secret-token", msg)


if __name__ == "__main__":
    unittest.main()
