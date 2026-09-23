import os
import unittest
from unittest.mock import AsyncMock, patch

from src import config, judge, main


class BackendSelectionTests(unittest.TestCase):
    def setUp(self):
        judge._BACKEND = None
        self.addCleanup(setattr, judge, "_BACKEND", None)

    def select(self, choice, key):
        env = {"TYPESAFE_API_KEY": key} if key else {}
        with patch.object(config, "JUDGE_BACKEND", choice), patch.dict(os.environ, env, clear=True):
            return judge._backend()

    def test_jev_is_the_default(self):
        with patch.object(judge, "JevBackend") as jev:
            self.assertIs(self.select("jev", "key"), jev.return_value)

    def test_missing_key_stops_instead_of_using_claude(self):
        with self.assertRaisesRegex(judge.JudgeBackendError, "TYPESAFE_API_KEY"):
            self.select("jev", None)

    def test_jev_startup_failure_stops_instead_of_using_claude(self):
        with patch.object(judge, "JevBackend", side_effect=RuntimeError("bad package")), \
             patch.object(judge, "LLMBackend") as llm:
            with self.assertRaisesRegex(judge.JudgeBackendError, "bad package"):
                self.select("jev", "key")
        llm.assert_not_called()

    def test_claude_only_when_explicitly_chosen(self):
        self.assertIsInstance(self.select("llm", None), judge.LLMBackend)

    def test_unknown_choice_is_rejected(self):
        with self.assertRaises(judge.JudgeBackendError):
            self.select("gpt", "key")

    def test_empty_env_var_means_jev(self):
        # GitHub passes an unset repository variable as "", which once
        # silently selected Claude for a whole run.
        import importlib
        with patch.dict(os.environ, {"JUDGE_BACKEND": "", "PYTHON_DOTENV_DISABLED": "1"}):
            self.assertEqual(importlib.reload(config).JUDGE_BACKEND, "jev")
        importlib.reload(config)


class PreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_judge_failure_stops_the_run_before_extraction(self):
        with patch.object(main.db, "migrate"), patch.object(main.db, "exclude_aged_out"), \
             patch("src.judge.preflight", AsyncMock(side_effect=judge.JudgeBackendError("no key"))), \
             patch.object(main, "_discover", AsyncMock()) as discover:
            with self.assertRaises(judge.JudgeBackendError):
                await main.main(["run"])
        discover.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
