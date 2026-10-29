"""Tests for EVIDEX helpers and its TUI shell."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidex import (
    ABOUT_TEXT,
    EvidexApp,
    ExtractionConfig,
    PromptScreen,
    discover_local_session,
    parse_proxy_url,
    safe_name,
)


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

    def test_proxy_url_parsing(self) -> None:
        proxy = parse_proxy_url("socks5://analyst:p%40ss@127.0.0.1:1080")
        self.assertEqual(proxy["proxy_type"], "socks5")
        self.assertEqual(proxy["addr"], "127.0.0.1")
        self.assertEqual(proxy["port"], 1080)
        self.assertEqual(proxy["username"], "analyst")
        self.assertEqual(proxy["password"], "p@ss")

    def test_proxy_url_rejects_unsupported_scheme(self) -> None:
        with self.assertRaisesRegex(ValueError, "scheme"):
            parse_proxy_url("ftp://127.0.0.1:21")

    def test_discovers_one_local_session(self) -> None:
        previous_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "existing.session"
            session.touch()
            try:
                os.chdir(temporary)
                self.assertEqual(discover_local_session(), str(session.resolve()))
            finally:
                os.chdir(previous_directory)

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

    async def test_about_screen_contains_developer_contact(self) -> None:
        self.assertIn("Developer: Akmal Taufik", ABOUT_TEXT)
        self.assertIn("work.akmaltaufik@gmail.com", ABOUT_TEXT)
        self.assertIn("@mohammadakmaltaufik", ABOUT_TEXT)

        app = EvidexApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("f3")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 2)

    async def test_connection_falls_back_to_https_transport(self) -> None:
        attempted: list[str] = []
        received_proxies: list[object] = []

        class FakeClient:
            def __init__(self, *args: object, connection: type, **kwargs: object) -> None:
                self.connection = connection
                self.connected = False
                received_proxies.append(kwargs.get("proxy"))

            async def connect(self) -> None:
                attempted.append(self.connection.__name__)
                if self.connection.__name__ != "ConnectionHttp":
                    raise OSError("simulated filtered transport")
                self.connected = True

            def is_connected(self) -> bool:
                return self.connected

            async def disconnect(self) -> None:
                self.connected = False

        config = ExtractionConfig(
            api_id=1,
            api_hash="test",
            phone="+10000000000",
            target="test",
            case_id="test",
            output_root=Path("."),
            message_limit=1,
            download_media=False,
            proxy=parse_proxy_url("socks5://127.0.0.1:1080"),
            session_path=None,
        )
        app = EvidexApp()
        app.set_status = lambda message: None  # type: ignore[method-assign]
        app.log_event = lambda message: None  # type: ignore[method-assign]

        with patch("evidex.TelegramClient", FakeClient):
            client = await app.connect_telegram(config, Path("unused"))

        self.assertTrue(client.is_connected())
        self.assertEqual(
            attempted,
            ["ConnectionTcpFull", "ConnectionTcpObfuscated", "ConnectionHttp"],
        )
        self.assertEqual(len(received_proxies), 3)
        self.assertTrue(all(proxy == config.proxy for proxy in received_proxies))


if __name__ == "__main__":
    unittest.main()
