"""Tests for EVIDEX helpers and its TUI shell."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from evidex import EvidexApp, PromptScreen, safe_name

class HelperTests(unittest.TestCase):
    def test_safe_name_removes_path_characters(self) -> None:
        self.assertEqual(safe_name(" ../Case 42/evidence "), "Case_42_evidence")

    def test_manifest_hashes_completed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            case_dir = Path(temporary)
            artifact = case_dir / "messages.txt"
            artifact.write_text("evidence\n", encoding="utf-8")

            EvidexApp().write_manifest(case_dir)

            expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
            manifest = (case_dir / "manifest.sha256").read_text(encoding="utf-8")
            self.assertEqual(manifest, f"{expected}  messages.txt\n")

class TuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_screen_and_legal_modal(self) -> None:
        app = EvidexApp()
        async with app.run_test(size=(120, 40)) as pilot:
            self.assertFalse(app.query_one("#start").disabled)
            await pilot.press("f1")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 2)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)

    async def test_authentication_prompt_returns_masked_input(self) -> None:
        app = EvidexApp()
        result: list[str | None] = []
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(
                PromptScreen("Verification", "Enter the Telegram code", password=True),
                result.append,
            )
            await pilot.pause()
            await pilot.press("1", "2", "3", "4", "enter")
            await pilot.pause()
            self.assertEqual(result, ["1234"])


if __name__ == "__main__":
    unittest.main()
