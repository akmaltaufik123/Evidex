"""Tests for EVIDEX helpers and its TUI shell."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from telethon.errors import ApiIdInvalidError
import evidex
import telegram_connection as connection

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

    async def test_connection_falls_back_to_http_mtproto_transport(self) -> None:
        attempted: list[str] = []
        received_proxies: list[object] = []

        class FakeClient:
            def __init__(self, *args: object, connection: type, **kwargs: object) -> None:
                self.session = SimpleNamespace(dc_id=2, port=443)
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

        with patch("telegram_connection.TelegramClient", FakeClient):
            client = await app.connect_telegram(config, Path("unused"))

        self.assertTrue(client.is_connected())
        self.assertEqual(
            attempted,
            ["ConnectionTcpFull", "ConnectionTcpObfuscated", "ConnectionHttp"],
        )
        self.assertEqual(len(received_proxies), 3)
        self.assertTrue(all(proxy == config.proxy for proxy in received_proxies))


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.config = ExtractionConfig(
            api_id=123456, api_hash="secret-hash", phone="+10000000000",
            target="test", case_id="test", output_root=Path("."),
            message_limit=1, download_media=False,
            proxy=parse_proxy_url("socks5://secret-user:secret-password@localhost:1080"),
            session_path=None,
        )
        self.app = EvidexApp()
        self.app.set_status = MagicMock()
        self.app.log_event = MagicMock()

    def client(self, error: BaseException | None = None) -> MagicMock:
        client = MagicMock()
        client.session = SimpleNamespace(dc_id=2, port=443)
        client.connect = AsyncMock(side_effect=error)
        client.disconnect = AsyncMock()
        client.is_connected.return_value = error is None
        return client

    async def test_success_preserves_client_and_configuration(self) -> None:
        client = self.client()
        with patch("telegram_connection.TelegramClient", return_value=client) as factory:
            result = await self.app.connect_telegram(self.config, Path("chosen"))
        self.assertIs(result, client)
        self.assertIs(self.app._active_client, client)
        client.disconnect.assert_not_awaited()
        args, kwargs = factory.call_args
        self.assertEqual(args, ("chosen", self.config.api_id, self.config.api_hash))
        self.assertEqual(kwargs["proxy"], self.config.proxy)

    async def test_cleanup_precedes_second_transport(self) -> None:
        first, second = self.client(OSError("failed")), self.client()
        def create(*args: object, **kwargs: object) -> MagicMock:
            if first.connect.await_count:
                first.disconnect.assert_awaited_once()
                return second
            return first
        with patch("telegram_connection.TelegramClient", side_effect=create):
            self.assertIs(await self.app.connect_telegram(self.config, Path("chosen")), second)
        second.disconnect.assert_not_awaited()

    async def test_cancellation_propagates_after_cleanup(self) -> None:
        client = self.client(asyncio.CancelledError())
        with patch("telegram_connection.TelegramClient", return_value=client) as factory:
            with self.assertRaises(asyncio.CancelledError):
                await self.app.connect_telegram(self.config, Path("chosen"))
        client.disconnect.assert_awaited_once()
        self.assertEqual(factory.call_count, 1)
        self.assertIsNone(self.app._active_client)

    async def test_invalid_credentials_are_not_network_timeouts(self) -> None:
        client = self.client(ApiIdInvalidError(request=None))
        with patch("telegram_connection.TelegramClient", return_value=client) as factory:
            with self.assertRaises(ApiIdInvalidError):
                await self.app.connect_telegram(self.config, Path("chosen"))
        client.disconnect.assert_awaited_once()
        self.assertEqual(factory.call_count, 1)
        self.assertIsNone(self.app._active_client)

    async def test_one_retry_policy_for_new_and_saved_sessions(self) -> None:
        original_wait_for = asyncio.wait_for
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "account.session"
            for existing in (False, True):
                if existing:
                    session.touch()
                with self.subTest(existing=existing):
                    with patch("telegram_connection.TelegramClient", return_value=self.client()) as factory, patch(
                        "telegram_connection.asyncio.wait_for", wraps=original_wait_for
                    ) as wait_for:
                        await self.app.connect_telegram(self.config, session)
                    kwargs = factory.call_args.kwargs
                    self.assertEqual(kwargs["connection_retries"], 1)
                    self.assertEqual(kwargs["timeout"], 10)
                    self.assertEqual(kwargs["request_retries"], 1)
                    self.assertEqual(wait_for.call_args.kwargs["timeout"], 60 if existing else 15)

    async def test_total_failure_has_safe_diagnostics(self) -> None:
        secret = f"{self.config.api_hash} {self.config.phone} secret-user secret-password code=12345"
        clients = [self.client(OSError(secret)) for _ in connection.TELEGRAM_TRANSPORTS]
        with patch("telegram_connection.TelegramClient", side_effect=clients):
            with self.assertRaises(ConnectionError) as caught:
                await self.app.connect_telegram(self.config, Path("chosen"))
        output = str(caught.exception) + str(self.app.log_event.call_args_list)
        for value in (self.config.api_hash, self.config.phone, "secret-user", "secret-password", "12345"):
            self.assertNotIn(value, output)
        for name, _ in connection.TELEGRAM_TRANSPORTS:
            self.assertIn(name, str(caught.exception))
        for client in clients:
            client.disconnect.assert_awaited_once()
        self.assertIsNone(self.app._active_client)

    async def test_managed_file_keeps_managed_policy_and_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "managed.session"
            session.write_bytes(b"session sentinel")
            with patch("telegram_connection.TelegramClient", return_value=self.client()) as factory:
                await self.app.connect_telegram(self.config, session)
            self.assertEqual(factory.call_args.kwargs["connection_retries"], 1)
            self.assertEqual(session.read_bytes(), b"session sentinel")
            self.assertIn("saved session", str(self.app.log_event.call_args_list))

    async def test_connect_does_not_authorize_account(self) -> None:
        client = self.client()
        with patch("telegram_connection.TelegramClient", return_value=client):
            await self.app.connect_telegram(self.config, Path("chosen"))
        client.is_user_authorized.assert_not_called()
        client.send_code_request.assert_not_called()
        self.assertIn("authorization pending", str(self.app.log_event.call_args_list))

    async def test_cleanup_failure_is_reported_safely(self) -> None:
        first, second = self.client(OSError("failed")), self.client()
        first.disconnect.side_effect = OSError("secret-password")
        with patch("telegram_connection.TelegramClient", side_effect=[first, second]):
            self.assertIs(await self.app.connect_telegram(self.config, Path("chosen")), second)
        output = str(self.app.log_event.call_args_list)
        self.assertIn("Cleanup:", output)
        self.assertNotIn("secret-password", output)

    async def test_outer_timeout_cleans_up_and_falls_back(self) -> None:
        first, second = self.client(), self.client()
        async def stall() -> None:
            await asyncio.Event().wait()
        first.connect.side_effect = stall
        with patch("telegram_connection.TRANSPORT_TIMEOUT_SECONDS", 0.01), patch(
            "telegram_connection.TelegramClient", side_effect=[first, second]
        ):
            self.assertIs(await self.app.connect_telegram(self.config, Path("chosen")), second)
        first.disconnect.assert_awaited_once()
        self.assertIn("connection timed out", str(self.app.log_event.call_args_list))


class AcquisitionFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_connects_authorizes_exports_and_hashes(self) -> None:
        import json
        from datetime import datetime, timezone
        client = MagicMock()
        client.session = SimpleNamespace(dc_id=2, port=443)
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.is_connected.return_value = True
        client.is_user_authorized = AsyncMock(return_value=True)
        client.get_entity = AsyncMock(return_value=SimpleNamespace(id=42, title="Fixture"))
        client.get_messages = AsyncMock(return_value=SimpleNamespace(total=1))
        message = SimpleNamespace(id=1, date=datetime.now(timezone.utc), edit_date=None,
            sender_id=7, post_author=None, raw_text="Fixture evidence", reply_to_msg_id=None,
            grouped_id=None, views=0, forwards=0, replies=None, media=None)
        async def messages(*args: object, **kwargs: object):
            yield message
        client.iter_messages.side_effect = messages
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = ExtractionConfig(1, "secret-hash", "+10000000000", "target", "fixture",
                                      root / "exports", 1, False, None, None)
            app = EvidexApp()
            with patch("telegram_connection.TelegramClient", return_value=client), patch("evidex.SESSION_DIR", root / "sessions"):
                async with app.run_test(size=(120, 40)):
                    worker = app.run_extraction(config)
                    await worker.wait()
                    self.assertFalse(app.query_one("#start").disabled)
                    self.assertIsNone(app._active_client)
            case = next((root / "exports").iterdir())
            report = json.loads((case / "acquisition_report.json").read_text())
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["messages_acquired"], 1)
            self.assertIn("Fixture evidence", (case / "messages.txt").read_text())
            for line in (case / "manifest.sha256").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(digest, hashlib.sha256((case / name).read_bytes()).hexdigest())
            self.assertNotIn(config.api_hash, (case / "metadata.json").read_text())
        client.is_user_authorized.assert_awaited_once()
        client.disconnect.assert_awaited_once()

    async def test_worker_total_failure_restores_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = ExtractionConfig(1, "test", "+10000000000", "target", "fixture",
                                      root / "exports", 1, False, None, None)
            app = EvidexApp()
            with patch("evidex.connect_client", new=AsyncMock(side_effect=ConnectionError("All Telegram transports failed"))), patch("evidex.SESSION_DIR", root / "sessions"):
                async with app.run_test(size=(120, 40)):
                    worker = app.run_extraction(config)
                    await worker.wait()
                    self.assertFalse(app.query_one("#start").disabled)
                    self.assertTrue(app.query_one("#cancel").disabled)
                    self.assertIsNone(app._active_client)
                    self.assertIsNone(app._extraction_worker)
            self.assertEqual(list((root / "exports").iterdir()), [])

    async def test_two_factor_authorization_stays_in_ui(self) -> None:
        from telethon.errors import SessionPasswordNeededError
        app = EvidexApp()
        app.set_status = MagicMock()
        app.log_event = MagicMock()
        app.push_screen_wait = AsyncMock(side_effect=["12345", "secret-password"])
        client = MagicMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        client.send_code_request = AsyncMock()
        client.sign_in = AsyncMock(side_effect=[SessionPasswordNeededError(request=None), None])
        await app.authorize_client(client, "+10000000000")
        self.assertEqual(client.sign_in.await_count, 2)
        client.sign_in.assert_awaited_with(password="secret-password")
        self.assertNotIn("secret-password", str(app.log_event.call_args_list))


class SimplifiedConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_constructor_failure_clears_active_client(self) -> None:
        active = MagicMock()
        with patch("telegram_connection.TelegramClient", side_effect=ValueError("invalid configuration")) as factory:
            with self.assertRaises(ValueError):
                await connection.connect_client(1, "test", Path("unused"), active=active, log=lambda message: None)
        self.assertEqual(factory.call_count, 1)
        active.assert_called_once_with(None)

    async def test_fresh_check_does_not_open_sqlite_or_authorize(self) -> None:
        client = MagicMock()
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.is_connected.return_value = True
        with patch("telegram_connection.TelegramClient", return_value=client) as factory, patch("builtins.print"):
            await connection.check_connection(1, "test")
        self.assertIsInstance(factory.call_args.args[0], connection.StringSession)
        self.assertIsNone(factory.call_args.kwargs["proxy"])
        client.send_code_request.assert_not_called()
        client.is_user_authorized.assert_not_called()
        client.disconnect.assert_awaited_once()

    async def test_timeout_override_is_validated_without_echoing_input(self) -> None:
        for value in ("nan", "inf", "-1", "0", "secret-password"):
            with self.subTest(value=value), patch.dict(os.environ, {"EVIDEX_CONNECT_TIMEOUT": value}):
                with self.assertRaises(ValueError) as caught:
                    connection.connection_timeout(False)
                self.assertEqual(str(caught.exception), "EVIDEX_CONNECT_TIMEOUT must be a finite number between 1 and 300")
        with patch.dict(os.environ, {"EVIDEX_CONNECT_TIMEOUT": "25"}):
            self.assertEqual(connection.connection_timeout(False), 25)
            self.assertEqual(connection.connection_timeout(True), 25)

    async def test_proxy_and_session_are_only_selected_explicitly(self) -> None:
        app = EvidexApp()
        with patch.dict(os.environ, {"ALL_PROXY": "socks5://hidden-password@localhost:1080", "EVIDEX_PROXY_URL": "", "EVIDEX_SESSION_PATH": ""}):
            async with app.run_test(size=(120, 40)):
                self.assertEqual(app.query_one("#proxy-url").value, "")
                self.assertEqual(app.query_one("#session-path").value, "")


class LauncherTests(unittest.TestCase):
    def test_default_launch_is_terminal(self) -> None:
        with patch("evidex.EvidexApp") as app:
            evidex.main([])
        app.return_value.run.assert_called_once_with()

    def test_browser_launch_uses_loopback_and_current_interpreter(self) -> None:
        import shlex
        import sys
        server_module = SimpleNamespace(Server=MagicMock())
        with patch.dict("sys.modules", {"textual_serve.server": server_module}), patch("evidex.EvidexApp") as app:
            evidex.main(["--web", "--port", "8080"])
        args, kwargs = server_module.Server.call_args
        self.assertEqual(shlex.split(args[0]), [sys.executable, str(Path(evidex.__file__).resolve())])
        self.assertEqual(kwargs, {"host": "127.0.0.1", "port": 8080, "title": "EVIDEX"})
        server_module.Server.return_value.serve.assert_called_once_with()
        app.assert_not_called()

    def test_missing_browser_dependency_has_install_instruction(self) -> None:
        import contextlib
        import io
        output = io.StringIO()
        with patch.dict("sys.modules", {"textual_serve": None, "textual_serve.server": None}), contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit) as caught:
                evidex.main(["--web"])
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("requirements-web.txt", output.getvalue())

    def test_connection_check_launches_without_ui_or_server(self) -> None:
        with patch.dict(os.environ, {"TELEGRAM_API_ID": "1", "TELEGRAM_API_HASH": "test"}), patch("evidex.check_connection", new=AsyncMock()) as check, patch("evidex.EvidexApp") as app:
            evidex.main(["--check-connection"])
        check.assert_awaited_once_with(1, "test")
        app.assert_not_called()

    def test_invalid_port_is_rejected(self) -> None:
        import contextlib
        import io
        for port in ("0", "65536"):
            with self.subTest(port=port), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    evidex.main(["--web", "--port", port])
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
