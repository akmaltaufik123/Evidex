"""Native localhost integration tests; no Telegram login or live credentials."""
import asyncio
import hashlib
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from aiohttp.test_utils import TestClient, TestServer
    from evidex_next import Engine, create_app, validate, TRANSPORTS, ENGINE_KEY, open_evidence_folder
except ModuleNotFoundError:
    Engine = None


PAYLOAD = dict(mode="acquire", api_id="1", api_hash="a" * 32,
               phone="+10000000000", target="fixture", authorized=True,
               case="fixture", limit="1", media=False)


def fake_client():
    client = MagicMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(id=42))
    client.send_code_request = AsyncMock()
    client.sign_in = AsyncMock()
    message = SimpleNamespace(id=1, date=datetime.now(timezone.utc), edit_date=None,
        sender_id=7, post_author=None, raw_text="Fixture evidence", reply_to_msg_id=None,
        grouped_id=None, views=0, forwards=0, replies=None, media=None)
    async def messages(*args, **kwargs):
        yield message
    client.iter_messages.side_effect = messages
    return client


@unittest.skipIf(Engine is None, "Install requirements-next.txt to test native browser mode")
class EngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {"EVIDEX_SESSION_DIR": str(self.root / "sessions"),
                                           "EVIDEX_EXPORT_DIR": str(self.root / "exports")})
        self.env.start()
        self.engine = Engine()

    async def asyncTearDown(self):
        await self.engine.close()
        self.env.stop()
        self.temporary.cleanup()

    async def wait_prompt(self, kind):
        async def wait():
            while self.engine.state["prompt"] != kind:
                await asyncio.sleep(0)
        await asyncio.wait_for(wait(), timeout=1)

    async def test_native_acquisition_exports_and_hashes(self):
        client = fake_client()
        with patch("evidex_next.connect_client", new=AsyncMock(return_value=client)) as connect:
            self.engine.start(validate(PAYLOAD))
            await self.engine.task
        self.assertEqual(self.engine.state["stage"], "complete")
        self.assertFalse(self.engine.state["busy"])
        self.assertEqual(self.engine.state["messages"], 1)
        case = Path(self.engine.state["output"])
        report = json.loads((case / "acquisition_report.json").read_text())
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["messages_acquired"], 1)
        for line in (case / "manifest.sha256").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(digest, hashlib.sha256((case / name).read_bytes()).hexdigest())
        self.assertEqual(connect.call_args.kwargs["transports"], TRANSPORTS)
        self.assertEqual(len(TRANSPORTS), 2)
        self.assertNotIn(PAYLOAD["api_hash"], json.dumps(self.engine.state))
        self.assertNotIn(PAYLOAD["phone"], (case / "metadata.json").read_text())
        client.disconnect.assert_awaited_once()

    async def test_media_attachment_is_hashed_including_manifest_filename(self):
        from evidence_store import write_manifest
        case = self.root / "case"
        (case / "media").mkdir(parents=True)
        attachment = case / "media" / "manifest.sha256"
        attachment.write_bytes(b"fixture attachment")
        write_manifest(case)
        self.assertIn("media/manifest.sha256", (case / "manifest.sha256").read_text())

    async def test_media_download_writes_attachment_hash(self):
        client = fake_client()
        original = client.iter_messages.side_effect
        async def messages(*args, **kwargs):
            async for message in original():
                message.media = SimpleNamespace()
                message.file = SimpleNamespace(name="sample.bin", mime_type="application/octet-stream", size=7)
                yield message
        async def download(message, file):
            path = Path(file) / "sample.bin"
            path.write_bytes(b"fixture")
            return str(path)
        client.iter_messages.side_effect = messages
        client.download_media = AsyncMock(side_effect=download)
        with patch("evidex_next.connect_client", new=AsyncMock(return_value=client)):
            self.engine.start(validate(dict(PAYLOAD, media=True)))
            await self.engine.task
        self.assertEqual(self.engine.state["stage"], "complete")
        self.assertEqual(self.engine.state["media"], 1)
        case = Path(self.engine.state["output"])
        record = json.loads((case / "messages.jsonl").read_text())
        self.assertEqual(record["media"]["sha256"], hashlib.sha256(b"fixture").hexdigest())
        self.assertEqual(record["media"]["saved_path"], "media/sample.bin")

    async def test_invalid_login_code_has_specific_safe_error(self):
        from telethon.errors import PhoneCodeInvalidError
        client = fake_client()
        client.is_user_authorized.return_value = False
        client.sign_in.side_effect = PhoneCodeInvalidError(request=None)
        with patch("evidex_next.connect_client", new=AsyncMock(return_value=client)):
            self.engine.start(validate(PAYLOAD))
            await self.wait_prompt("code")
            self.engine.respond("secret-code")
            await self.engine.task
        self.assertEqual(self.engine.state["stage"], "failed")
        self.assertIn("verification code", self.engine.state["error"])
        self.assertNotIn("secret-code", json.dumps(self.engine.state))

    async def test_fresh_test_ignores_session_and_proxy_without_login(self):
        from telethon.sessions import StringSession
        client = fake_client()
        payload = dict(PAYLOAD, mode="test", session="missing.session", proxy="not-a-proxy")
        with patch("evidex_next.connect_client", new=AsyncMock(return_value=client)) as connect:
            self.engine.start(validate(payload))
            await self.engine.task
        self.assertIsInstance(connect.call_args.args[2], StringSession)
        self.assertIsNone(connect.call_args.kwargs["proxy"])
        self.assertEqual(self.engine.state["stage"], "transport_passed")
        client.is_user_authorized.assert_not_called()
        client.get_entity.assert_not_called()
        self.assertFalse((self.root / "sessions").exists())
        self.assertFalse((self.root / "exports").exists())

    async def test_login_and_two_factor_stay_on_job_loop(self):
        from telethon.errors import SessionPasswordNeededError
        client = fake_client()
        client.is_user_authorized.side_effect = [False, True]
        client.sign_in.side_effect = [SessionPasswordNeededError(request=None), None]
        with patch("evidex_next.connect_client", new=AsyncMock(return_value=client)):
            self.engine.start(validate(PAYLOAD))
            await self.wait_prompt("code")
            self.engine.respond("12345")
            await self.wait_prompt("password")
            self.engine.respond("secret-password")
            await self.engine.task
        self.assertEqual(self.engine.state["stage"], "complete")
        client.sign_in.assert_awaited_with(password="secret-password")
        for value in ("secret-password", "12345", PAYLOAD["api_hash"]):
            self.assertNotIn(value, json.dumps(self.engine.state))

    async def test_cancel_login_cleans_up_and_allows_restart(self):
        client = fake_client()
        client.is_user_authorized.return_value = False
        with patch("evidex_next.connect_client", new=AsyncMock(return_value=client)):
            self.engine.start(validate(PAYLOAD))
            await self.wait_prompt("code")
            self.engine.cancel()
            self.engine.cancel()  # Repeated clicks must not interrupt cleanup.
            await self.engine.task
        self.assertEqual(self.engine.state["stage"], "cancelled")
        self.assertFalse(self.engine.state["busy"])
        self.assertIsNone(self.engine.answer)
        client.disconnect.assert_awaited_once()

    async def test_cancel_immediately_does_not_leave_busy_state(self):
        self.engine.start(validate(PAYLOAD))
        self.engine.cancel()
        await asyncio.gather(self.engine.task, return_exceptions=True)
        await asyncio.sleep(0)
        self.assertFalse(self.engine.state["busy"])
        self.assertEqual(self.engine.state["stage"], "cancelled")

    async def test_partial_acquisition_is_finalized_on_shutdown(self):
        client = fake_client()
        original = client.iter_messages.side_effect
        yielded = asyncio.Event()
        async def messages(*args, **kwargs):
            async for message in original():
                yield message
            yielded.set()
            await asyncio.Event().wait()
        client.iter_messages.side_effect = messages
        with patch("evidex_next.connect_client", new=AsyncMock(return_value=client)):
            self.engine.start(validate(PAYLOAD))
            await asyncio.wait_for(yielded.wait(), timeout=1)
            await self.engine.close()
        case = Path(self.engine.state["output"])
        report = json.loads((case / "acquisition_report.json").read_text())
        self.assertEqual(report["status"], "cancelled")
        self.assertEqual(report["messages_acquired"], 1)
        self.assertTrue((case / "manifest.sha256").is_file())
        self.assertFalse(self.engine.state["busy"])

    async def test_failure_does_not_expose_exception_secrets(self):
        with patch("evidex_next.connect_client", new=AsyncMock(side_effect=OSError("secret-password " + PAYLOAD["api_hash"]))):
            self.engine.start(validate(PAYLOAD))
            await self.engine.task
        self.assertEqual(self.engine.state["stage"], "failed")
        self.assertFalse(self.engine.state["busy"])
        self.assertNotIn("secret-password", json.dumps(self.engine.state))
        self.assertNotIn(PAYLOAD["api_hash"], json.dumps(self.engine.state))

    async def test_existing_session_not_replaced_or_opened_by_validation(self):
        session = self.root / "existing.session"
        session.write_bytes(b"existing account sentinel")
        config = validate(dict(PAYLOAD, session=str(session)))
        self.assertEqual(config["session"], session.resolve())
        self.assertEqual(session.read_bytes(), b"existing account sentinel")
        with self.assertRaises(ValueError):
            validate(dict(PAYLOAD, session=str(self.root / "missing.session")))


@unittest.skipIf(Engine is None, "Install requirements-next.txt to test native browser mode")
class NativeHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {"EVIDEX_EXPORT_DIR": str(self.root)})
        self.env.start()
        self.app = create_app()
        self.client = TestClient(TestServer(self.app, host="127.0.0.1"))
        await self.client.start_server()
        response = await self.client.get("/")
        self.html = await response.text()
        self.token = re.search(r"const token='([^']+)'", self.html).group(1)
        self.headers = {"X-Evidex-Token": self.token}

    async def asyncTearDown(self):
        await self.client.close()
        self.env.stop()
        self.temporary.cleanup()

    def saved_case(self):
        case = self.root / "EVIDEX_previous_job"
        case.mkdir()
        (case / "acquisition_report.json").write_text(json.dumps({"status": "complete"}))
        (case / "messages.txt").write_text("Evidence sentinel")
        return case

    async def test_stylesheet_route_and_policy_allow_locked_theme(self):
        response = await self.client.get("/app.css")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/css")
        self.assertTrue((await response.text()).startswith("/* Hallmark"))
        response = await self.client.get("/")
        self.assertIn("style-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn('href="/app.css"', await response.text())

    async def test_bilingual_catalog_and_all_six_guide_images_are_served(self):
        match = re.search(r'<script type="application/json" id="i18n">(.*?)</script>', self.html, re.S)
        content = json.loads(match.group(1))
        self.assertEqual(set(content["en"]), set(content["ms"]))
        self.assertEqual(len(content["guide"]), 6)
        self.assertNotIn("__COPY__", self.html)
        for page in content["guide"]:
            response = await self.client.get("/guide-assets/" + page["image"])
            self.assertEqual(response.status, 200)
            self.assertEqual(response.content_type, "image/webp")
            self.assertGreater(len(await response.read()), 1000)
        self.assertEqual((await self.client.get("/guide-assets/not-an-image.txt")).status, 404)

    async def test_message_reader_search_pagination_and_integrity(self):
        case = self.saved_case()
        records = [dict(message_id=n, sender_id=7, date_utc="2026-10-30T00:00:00+00:00",
                        text="needle <script>example</script>" if n == 3 else "Fixture text", media=None) for n in range(55)]
        path = case / "messages.jsonl"
        path.write_text("\n".join(json.dumps(item) for item in records) + "\n")
        before = path.read_bytes()
        response = await self.client.get("/api/messages", headers=self.headers, params={"case": case.name})
        data = await response.json()
        self.assertEqual(len(data["messages"]), 50)
        self.assertTrue(data["more"])
        response = await self.client.get("/api/messages", headers=self.headers, params={"case": case.name, "offset": "50"})
        data = await response.json()
        self.assertEqual(len(data["messages"]), 5)
        self.assertFalse(data["more"])
        response = await self.client.get("/api/messages", headers=self.headers, params={"case": case.name, "q": "NEEDLE"})
        data = await response.json()
        self.assertEqual([item["message_id"] for item in data["messages"]], [3])
        self.assertEqual(before, path.read_bytes())
        self.assertEqual((await self.client.get("/api/messages", headers=self.headers, params={"case": case.name, "offset": "-1"})).status, 400)
        self.assertEqual((await self.client.get("/api/messages", params={"case": case.name})).status, 403)

    async def test_attachment_download_is_limited_to_case_media(self):
        case = self.saved_case()
        (case / "media").mkdir()
        attachment = case / "media" / "sample.bin"
        attachment.write_bytes(b"fixture attachment")
        response = await self.client.get("/api/attachment", headers=self.headers, params={"case": case.name, "path": "media/sample.bin"})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.read(), b"fixture attachment")
        self.assertEqual(response.headers["Content-Disposition"], "attachment")
        for relative in ("../outside", "messages.txt", "/etc/passwd"):
            response = await self.client.get("/api/attachment", headers=self.headers, params={"case": case.name, "path": relative})
            self.assertEqual(response.status, 404)
        self.assertEqual(attachment.read_bytes(), b"fixture attachment")

    async def test_saved_results_survive_server_state_reset(self):
        case = self.saved_case()
        response = await self.client.get("/api/results", headers=self.headers)
        self.assertEqual(response.status, 200)
        results = (await response.json())["cases"]
        self.assertEqual(results, [{"name": case.name, "path": str(case), "status": "complete"}])
        self.assertEqual(self.app[ENGINE_KEY].state["stage"], "idle")

    async def test_results_ignore_broken_links_and_malformed_reports(self):
        case = self.saved_case()
        (self.root / "EVIDEX_broken").symlink_to(self.root / "missing")
        malformed = self.root / "EVIDEX_malformed"
        malformed.mkdir()
        (malformed / "acquisition_report.json").write_text("invalid json")
        response = await self.client.get("/api/results", headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["name"] for item in (await response.json())["cases"]], [case.name])

    async def test_open_saved_folder_does_not_change_evidence(self):
        case = self.saved_case()
        before = {p.name: p.read_bytes() for p in case.iterdir()}
        with patch("evidex_next.open_evidence_folder", new=AsyncMock()) as opener:
            response = await self.client.post("/api/open-folder", headers=self.headers, json={"case": case.name})
        self.assertEqual(response.status, 200)
        opener.assert_awaited_once_with(case)
        self.assertEqual((await response.json())["path"], str(case))
        self.assertEqual(before, {p.name: p.read_bytes() for p in case.iterdir()})

    async def test_folder_open_requires_token_and_rejects_arbitrary_paths(self):
        case = self.saved_case()
        self.assertEqual((await self.client.post("/api/open-folder", json={"case": case.name})).status, 403)
        with patch("evidex_next.open_evidence_folder", new=AsyncMock()) as opener:
            for value in ("../outside", str(case), "EVIDEX_missing", None):
                response = await self.client.post("/api/open-folder", headers=self.headers, json={"case": value})
                self.assertEqual(response.status, 400)
            opener.assert_not_called()

    async def test_symlink_cannot_open_folder_outside_exports(self):
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside)
            (path / "acquisition_report.json").write_text('{"status":"complete"}')
            (self.root / "EVIDEX_escape").symlink_to(path, target_is_directory=True)
            with patch("evidex_next.open_evidence_folder", new=AsyncMock()) as opener:
                response = await self.client.post("/api/open-folder", headers=self.headers, json={"case": "EVIDEX_escape"})
                self.assertEqual(response.status, 400)
                opener.assert_not_called()

    async def test_missing_file_manager_has_manual_path_fallback(self):
        case = self.saved_case()
        with patch("evidex_next.open_evidence_folder", new=AsyncMock(side_effect=OSError("internal-secret"))):
            response = await self.client.post("/api/open-folder", headers=self.headers, json={"case": case.name})
        self.assertEqual(response.status, 503)
        error = (await response.json())["error"]
        self.assertIn(str(case), error)
        self.assertNotIn("internal-secret", error)

    async def test_open_folder_is_blocked_during_acquisition(self):
        case = self.saved_case()
        self.app[ENGINE_KEY].state["busy"] = True
        with patch("evidex_next.open_evidence_folder", new=AsyncMock()) as opener:
            response = await self.client.post("/api/open-folder", headers=self.headers, json={"case": case.name})
        self.assertEqual(response.status, 409)
        opener.assert_not_called()

    async def test_page_and_polling_require_no_websocket_bridge(self):
        self.assertIn("EVIDEX Next", self.html)
        self.assertNotIn("new WebSocket", self.html)
        response = await self.client.get("/api/state", headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["stage"], "idle")

    async def test_requests_without_token_or_with_foreign_host_rejected(self):
        self.assertEqual((await self.client.get("/api/state")).status, 403)
        self.assertEqual((await self.client.get("/", headers={"Host": "evil.example"})).status, 403)

    async def test_validation_does_not_reflect_secret_inputs(self):
        response = await self.client.post("/api/run", headers=self.headers, json={"api_id": "secret-password"})
        self.assertEqual(response.status, 400)
        self.assertNotIn("secret-password", await response.text())

    async def test_http_test_and_page_reload_preserve_running_job(self):
        gate = asyncio.Event()
        client = fake_client()
        async def connect(*args, **kwargs):
            await gate.wait()
            return client
        with patch("evidex_next.connect_client", side_effect=connect):
            response = await self.client.post("/api/run", headers=self.headers, json=dict(PAYLOAD, mode="test"))
            self.assertEqual(response.status, 200)
            response = await self.client.get("/")
            self.assertEqual(response.status, 200)
            response = await self.client.post("/api/run", headers=self.headers, json=dict(PAYLOAD, mode="test"))
            self.assertEqual(response.status, 400)
            response = await self.client.get("/api/state", headers=self.headers)
            self.assertTrue((await response.json())["busy"])
            gate.set()
            await self.app[ENGINE_KEY].task
        response = await self.client.get("/api/state", headers=self.headers)
        self.assertEqual((await response.json())["stage"], "transport_passed")


@unittest.skipIf(Engine is None, "Install requirements-next.txt")
class FolderOpenerTests(unittest.IsolatedAsyncioTestCase):
    async def test_wsl_uses_windows_path_and_argument_list(self):
        folder = Path("/home/user/evidence with spaces")
        commands = {"explorer.exe": "/interop/explorer.exe", "wslpath": "/usr/bin/wslpath"}
        with patch("evidex_next.sys.platform", "linux"), patch("evidex_next.shutil.which", side_effect=commands.get), patch(
            "evidex_next.folder_command", new=AsyncMock(side_effect=[b"\\\\wsl.localhost\\Kali\\home\\user\\case\n", b""])
        ) as command:
            await open_evidence_folder(folder)
        self.assertEqual(command.await_args_list[0].args, ("/usr/bin/wslpath", "-w", str(folder)))
        self.assertEqual(command.await_args_list[1].args, ("/interop/explorer.exe", "\\\\wsl.localhost\\Kali\\home\\user\\case"))

    async def test_linux_uses_local_file_manager_without_shell(self):
        folder = Path("/tmp/evidence ; file")
        with patch("evidex_next.sys.platform", "linux"), patch("evidex_next.shutil.which", side_effect=lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None), patch(
            "evidex_next.folder_command", new=AsyncMock()
        ) as command:
            await open_evidence_folder(folder)
        command.assert_awaited_once_with("/usr/bin/xdg-open", str(folder))
