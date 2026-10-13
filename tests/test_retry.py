import unittest
from retry import call_with_fallback, BusyError


class Flaky:
    def __init__(self, fail_models=(), fail_times=0):
        self.fail_models, self.fail_times, self.calls = set(fail_models), fail_times, []

    def __call__(self, model):
        self.calls.append(model)
        if model in self.fail_models or len(self.calls) <= self.fail_times:
            raise RuntimeError("503 UNAVAILABLE high demand")
        return "ok"


class RetryTests(unittest.TestCase):
    def test_retries_same_model_then_succeeds(self):
        f = Flaky(fail_times=2)
        self.assertEqual(call_with_fallback(f, ["m1"], attempts=3, sleep=lambda s: None), "ok")
        self.assertEqual(f.calls, ["m1", "m1", "m1"])

    def test_falls_back_to_next_model(self):
        f = Flaky(fail_models=["m1"])
        self.assertEqual(call_with_fallback(f, ["m1", "m2"], attempts=2, sleep=lambda s: None), "ok")
        self.assertEqual(f.calls, ["m1", "m1", "m2"])

    def test_all_busy_raises_busy_error(self):
        with self.assertRaises(BusyError):
            call_with_fallback(Flaky(fail_models=["m1", "m2"]), ["m1", "m2"], attempts=2,
                               sleep=lambda s: None)

    def test_dropped_connection_counts_as_busy(self):
        calls = []

        def drop(model):
            calls.append(model)
            if len(calls) == 1:
                raise RuntimeError("httpcore.RemoteProtocolError: Server disconnected without sending a response.")
            return "ok"
        self.assertEqual(call_with_fallback(drop, ["m1"], attempts=2, sleep=lambda s: None), "ok")

    def test_unavailable_model_is_skipped_without_retrying(self):
        calls = []

        def fn(model):
            calls.append(model)
            if model == "old":
                raise RuntimeError("404 NOT_FOUND. This model is no longer available")
            return "ok"
        self.assertEqual(call_with_fallback(fn, ["old", "new"], attempts=3, sleep=lambda s: None), "ok")
        self.assertEqual(calls, ["old", "new"])

    def test_models_from_env_default_chain_and_override(self):
        import os
        from unittest import mock
        from retry import models_from_env
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(models_from_env()[0], "gemini-3.8-flash")
            self.assertGreaterEqual(len(models_from_env()), 3)
        with mock.patch.dict(os.environ, {"GEMINI_MODELS": "a, b"}, clear=True):
            self.assertEqual(models_from_env(), ["a", "b"])

    def test_quota_and_other_errors_propagate_immediately(self):
        def boom(model):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        with self.assertRaises(RuntimeError) as cm:
            call_with_fallback(boom, ["m1", "m2"], attempts=3, sleep=lambda s: None)
        self.assertNotIsInstance(cm.exception, BusyError)


if __name__ == "__main__":
    unittest.main()
