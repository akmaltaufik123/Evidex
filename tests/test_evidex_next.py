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
    from evidex_next import Engine, create_app, validate, TRANSPORTS, ENGINE_KEY
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
        self.app = create_app()
        self.client = TestClient(TestServer(self.app, host="127.0.0.1"))
        await self.client.start_server()
        response = await self.client.get("/")
        self.html = await response.text()
        self.token = re.search(r"const token='([^']+)'", self.html).group(1)
        self.headers = {"X-Evidex-Token": self.token}

    async def asyncTearDown(self):
        await self.client.close()

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
