"""EVIDEX Next: one localhost server, one asyncio loop, one acquisition at a time."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
from datetime import timezone
from pathlib import Path
from typing import Any

from aiohttp import web
from telethon.errors import (
    ApiIdInvalidError, FloodWaitError, SessionPasswordNeededError,
    PhoneCodeInvalidError, PhoneCodeExpiredError, PasswordHashInvalidError,
)
from telethon.sessions import StringSession

from evidence_excel import write_excel
from evidence_store import utc_now, safe_name, sha256_file, write_json, write_manifest
from telegram_connection import (
    TELEGRAM_TRANSPORTS, connect_client, disconnect_client,
    connection_error_detail, parse_proxy_url,
)

VERSION = "0.2.3"
# Both TCP transports worked in the operator's standalone test. HTTP/TLS did not.
TRANSPORTS = TELEGRAM_TRANSPORTS[:2]


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy only accepted values; never reflect credentials in validation errors."""
    mode = payload.get("mode", "test")
    if mode not in {"test", "acquire"}:
        raise ValueError("Choose a connection test or acquisition.")
    api_id = str(payload.get("api_id", "")).strip()
    api_hash = str(payload.get("api_hash", "")).strip()
    if not api_id.isascii() or not api_id.isdigit() or int(api_id) <= 0:
        raise ValueError("API ID must be a positive number.")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        raise ValueError("API hash must contain 32 hexadecimal characters.")
    config = {"mode": mode, "api_id": int(api_id), "api_hash": api_hash}
    if mode == "test":
        return config  # Explicit fresh/direct check, regardless of other fields.
    if payload.get("authorized") is not True:
        raise ValueError("Confirm authorization before acquisition.")
    phone = str(payload.get("phone", "")).strip()
    target = str(payload.get("target", "")).strip()
    if not re.fullmatch(r"\+[0-9]{7,15}", phone) or not target:
        raise ValueError("Enter a phone number in international format and a target.")
    limit = str(payload.get("limit", "")).strip()
    if limit and (not limit.isascii() or not limit.isdigit() or int(limit) <= 0):
        raise ValueError("Message limit must be a positive number or blank.")
    session = str(payload.get("session", "")).strip()
    if session:
        path = Path(session).expanduser().resolve()
        if path.suffix != ".session" or not path.is_file():
            raise ValueError("Select an existing .session file, or leave the field blank.")
    else:
        directory = Path(os.getenv("EVIDEX_SESSION_DIR", ".evidex_sessions"))
        path = directory / ("evidex_" + hashlib.sha256(phone.encode()).hexdigest()[:12])
    proxy_text = str(payload.get("proxy", "")).strip()
    case_name = str(payload.get("case", "")).strip() or "case"
    if len(case_name) > 120 or any(ord(char) < 32 for char in case_name):
        raise ValueError("Evidence name must be at most 120 characters without control characters.")
    config.update(phone=phone, target=target, session=path,
                  proxy=parse_proxy_url(proxy_text) if proxy_text else None,
                  limit=int(limit) if limit else None,
                  case=safe_name(case_name), case_name=case_name,
                  output=Path(os.getenv("EVIDEX_EXPORT_DIR", "evidence_exports")),
                  media=payload.get("media") is True)
    return config


class Engine:
    """All Telethon calls, prompts and cancellation stay on the server's event loop."""
    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.answer: asyncio.Future | None = None
        self.state: dict[str, Any] = {}
        self.reset()

    def reset(self) -> None:
        self.state = dict(stage="idle", busy=False, prompt=None, messages=0,
                          media=0, output=None, error=None, logs=[])

    def log(self, message: str) -> None:
        self.state["logs"] = (self.state["logs"] + [f"{utc_now():%H:%M:%S} UTC · {message}"])[-100:]

    def start(self, config: dict[str, Any]) -> None:
        if self.task is not None and not self.task.done():
            raise ValueError("A job is already running. Cancel it or wait for completion.")
        self.reset()
        self.state.update(stage="connecting", busy=True, mode=config["mode"])
        self.task = asyncio.create_task(self.run(config))
        self.task.add_done_callback(self.finished)

    def finished(self, task: asyncio.Task) -> None:
        if self.task is task and task.cancelled():
            self.state.update(stage="cancelled", busy=False, prompt=None)

    async def prompt(self, kind: str) -> str:
        self.state.update(stage="login", prompt=kind)
        self.answer = asyncio.get_running_loop().create_future()
        try:
            return await self.answer
        finally:
            self.answer = None
            self.state["prompt"] = None

    def respond(self, value: str) -> None:
        if self.answer is None or self.answer.done():
            raise ValueError("There is no login prompt waiting for an answer.")
        if not value.strip():
            raise ValueError("Enter a value for the login prompt.")
        self.answer.set_result(value)

    def cancel(self) -> None:
        if self.task is not None and not self.task.done() and not self.task.cancelling():
            self.task.cancel()

    async def close(self) -> None:
        self.cancel()
        if self.task is not None:
            await asyncio.gather(self.task, return_exceptions=True)

    async def run(self, config: dict[str, Any]) -> None:
        client = None
        try:
            testing = config["mode"] == "test"
            session = StringSession() if testing else config["session"]
            if not testing:
                session.parent.mkdir(parents=True, exist_ok=True)
            self.log("Fresh direct transport test; no login or saved session." if testing
                     else "Connecting to the selected account session.")
            client = await connect_client(
                config["api_id"], config["api_hash"], session,
                proxy=None if testing else config["proxy"],
                transports=TRANSPORTS, log=self.log,
            )
            if testing:
                self.state["stage"] = "transport_passed"
                self.log("PASS: transport connected. Account authorization was not tested.")
                return
            self.state["stage"] = "authorizing"
            if not await client.is_user_authorized():
                await client.send_code_request(config["phone"])
                code = await self.prompt("code")
                try:
                    await client.sign_in(phone=config["phone"], code=code)
                except SessionPasswordNeededError:
                    password = await self.prompt("password")
                    await client.sign_in(password=password)
            if not await client.is_user_authorized():
                raise ValueError("Authorization did not complete")
            self.log("Account authorization confirmed.")
            self.state["stage"] = "acquiring"
            await self.acquire(client, config)
            self.state["stage"] = "complete"
            self.log("Acquisition completed; integrity manifest finalized.")
        except asyncio.CancelledError:
            self.state["stage"] = "cancelled"
            self.log("Cancelled; any acquired evidence has been finalized.")
        except ApiIdInvalidError:
            self.state.update(stage="failed", error="Telegram rejected the API ID or API hash.")
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            self.state.update(stage="failed", error="Telegram verification code is invalid or expired. Start again to request a new code.")
        except PasswordHashInvalidError:
            self.state.update(stage="failed", error="Telegram rejected the two-factor password.")
        except FloodWaitError as error:
            self.state.update(stage="failed", error=f"Telegram rate limit: wait {error.seconds} seconds.")
        except Exception as error:
            self.state.update(stage="failed", error=connection_error_detail(error))
        finally:
            if client is not None:
                await disconnect_client(client, self.log)
            self.state.update(busy=False, prompt=None)
            if self.state["error"]:
                self.log(self.state["error"])

    async def acquire(self, client: Any, config: dict[str, Any]) -> None:
        target = config["target"]
        entity = await client.get_entity(int(target) if target.lstrip("-").isdigit() else target)
        root = config["output"]
        root.mkdir(parents=True, exist_ok=True)
        started = utc_now().isoformat()
        # Exclusive mkdir: a new job never overwrites an existing evidence case.
        case = root / f"EVIDEX_{config['case']}_{utc_now():%Y%m%dT%H%M%S}_{secrets.token_hex(4)}"
        case.mkdir()
        self.state["output"] = str(case.resolve())
        metadata = dict(tool="EVIDEX Next", tool_version=VERSION, case_id=config["case"], case_name=config.get("case_name", config["case"]),
                        acquisition_started_utc=started, source={"platform": "Telegram",
                        "requested_target": target, "entity_id": getattr(entity, "id", None)},
                        settings={"ordering": "oldest_to_newest", "message_limit": config["limit"],
                                  "download_media": config["media"], "proxy_used": config["proxy"] is not None})
        status, failure, media_errors = "failed", None, 0
        try:
            write_json(case / "metadata.json", metadata)
            if config["media"]:
                (case / "media").mkdir()
            with (case / "messages.jsonl").open("w", encoding="utf-8") as jsonl, (case / "messages.txt").open("w", encoding="utf-8") as text:
                async for message in client.iter_messages(entity, limit=config["limit"], reverse=True):
                    media = None
                    if message.media is not None:
                        media = {"telegram_type": type(message.media).__name__,
                                 "name": getattr(message.file, "name", None),
                                 "mime_type": getattr(message.file, "mime_type", None),
                                 "size_bytes": getattr(message.file, "size", None)}
                        if config["media"]:
                            try:
                                saved = await client.download_media(message, file=str(case / "media"))
                                if saved:
                                    path = Path(saved).resolve()
                                    media.update(saved_path=path.relative_to(case.resolve()).as_posix(), sha256=sha256_file(path))
                                    self.state["media"] += 1
                            except Exception as error:
                                media_errors += 1
                                media["download_error"] = type(error).__name__
                    def date(value: Any) -> str | None:
                        if value is None:
                            return None
                        if value.tzinfo is None:
                            value = value.replace(tzinfo=timezone.utc)
                        return value.astimezone(timezone.utc).isoformat()
                    record = dict(message_id=message.id, date_utc=date(message.date), edit_date_utc=date(message.edit_date),
                                  sender_id=message.sender_id, post_author=message.post_author,
                                  text=message.raw_text or "", reply_to_message_id=message.reply_to_msg_id,
                                  grouped_id=message.grouped_id, views=message.views, forwards=message.forwards,
                                  replies=getattr(message.replies, "replies", None), media=media)
                    jsonl.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                    text.write(f"[{record['date_utc']}] message={message.id} sender={message.sender_id}\n{record['text']}\n")
                    self.state["messages"] += 1
            status = "complete"
        except asyncio.CancelledError:
            status, failure = "cancelled", "Cancelled by operator"
            raise
        except Exception as error:
            failure = connection_error_detail(error)
            raise
        finally:
            excel_error = None
            try:
                write_excel(case, config.get("case_name", config["case"]))
            except Exception as error:
                excel_error = error
                status, failure = "failed", "Excel export failed: " + type(error).__name__
            report = dict(case_name=config.get("case_name", config["case"]), case_id=config["case"], status=status, started_utc=started,
                          finished_utc=utc_now().isoformat(), messages_acquired=self.state["messages"],
                          media_files_acquired=self.state["media"], media_download_errors=media_errors, failure=failure)
            metadata.update(acquisition_status=status, result=report)
            write_json(case / "metadata.json", metadata)
            write_json(case / "acquisition_report.json", report)
            write_manifest(case)
            if excel_error is not None:
                raise excel_error


def evidence_root() -> Path:
    return Path(os.getenv("EVIDEX_EXPORT_DIR", "evidence_exports")).resolve()


def evidence_case(name: str) -> Path:
    """Only allow an existing case directly inside the configured export root."""
    root = evidence_root()
    if not isinstance(name, str) or not name.startswith("EVIDEX_") or Path(name).name != name:
        raise ValueError("Invalid evidence case")
    if (root / name).is_symlink():
        raise ValueError("Evidence links cannot be used")
    case = (root / name).resolve()
    if case.parent != root or not case.is_dir() or not (case / "acquisition_report.json").is_file():
        raise ValueError("Evidence case is unavailable")
    return case


def recent_evidence() -> list[dict[str, Any]]:
    root = evidence_root()
    if not root.is_dir():
        return []
    history = root / ".hidden_history.json"
    hidden = set(json.loads(history.read_text(encoding="utf-8")).get("cases", [])) if history.is_file() else set()
    results = []
    for path in sorted(root.glob("EVIDEX_*"), key=lambda item: item.lstat().st_mtime, reverse=True):
        try:
            case = evidence_case(path.name)
            if case.name in hidden:
                continue
            report = json.loads((case / "acquisition_report.json").read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                continue
            results.append(dict(name=case.name, path=str(case), status=report.get("status", "unknown")))
        except (OSError, ValueError):
            continue
        if len(results) == 50:
            break
    return results


async def folder_command(*args: str) -> bytes:
    """Run fixed opener arguments without a shell and without blocking acquisition."""
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise OSError("File manager command failed")
    return stdout


async def open_evidence_folder(case: Path) -> None:
    if sys.platform == "win32":
        await asyncio.to_thread(os.startfile, str(case))
    elif shutil.which("explorer.exe"):
        # Windows Explorer needs a Windows/WSL UNC path, not /home/… .
        converter = shutil.which("wslpath")
        if not converter:
            raise OSError("WSL path converter is unavailable")
        windows_path = (await folder_command(converter, "-w", str(case))).decode().strip()
        if not windows_path:
            raise OSError("WSL path conversion failed")
        await folder_command(shutil.which("explorer.exe"), windows_path)
    else:
        executable = shutil.which("open" if sys.platform == "darwin" else "xdg-open")
        if not executable:
            raise OSError("File manager is unavailable")
        await folder_command(executable, str(case))


ENGINE_KEY = web.AppKey("engine", Engine)


def create_app() -> web.Application:
    engine, token = Engine(), secrets.token_urlsafe(32)

    @web.middleware
    async def local_only(request: web.Request, handler):
        # A per-launch token and exact Host check block other websites from using
        # the unauthenticated local service as a credential or acquisition proxy.
        expected = f"127.0.0.1:{request.transport.get_extra_info('sockname')[1]}"
        if request.host != expected:
            raise web.HTTPForbidden(text="Use the printed 127.0.0.1 URL.")
        if request.path.startswith("/api/") and not secrets.compare_digest(request.headers.get("X-Evidex-Token", ""), token):
            raise web.HTTPForbidden(text="Reload the EVIDEX page.")
        try:
            return await handler(request)
        except (ValueError, json.JSONDecodeError):
            return web.json_response({"error": "Invalid request. Check the form fields and selected session."}, status=400)

    app = web.Application(middlewares=[local_only], client_max_size=32 * 1024)
    app[ENGINE_KEY] = engine

    async def index(request):
        html = Path(__file__).with_suffix(".html").read_text(encoding="utf-8")
        content = Path(__file__).with_name("evidex_next_content.json").read_text(encoding="utf-8")
        # The trusted translation catalog is JSON, not executable HTML.
        catalog = json.dumps(json.loads(content), ensure_ascii=False).replace("<", r"\u003c")
        return web.Response(text=html.replace("__TOKEN__", token).replace("__COPY__", catalog), content_type="text/html", headers={
            "Cache-Control": "no-store", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"})

    async def state(request):
        return web.json_response(engine.state, headers={"Cache-Control": "no-store"})

    async def run(request):
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError()
        try:
            config = validate(payload)
            engine.start(config)
        except ValueError as error:
            # Validation errors are fixed messages authored here or in proxy parsing.
            return web.json_response({"error": str(error)}, status=400)
        return web.json_response({"ok": True})

    async def answer(request):
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
            raise ValueError()
        engine.respond(payload["answer"])
        return web.json_response({"ok": True})

    async def cancel(request):
        engine.cancel()
        return web.json_response({"ok": True})

    async def results(request):
        return web.json_response({"cases": recent_evidence()}, headers={"Cache-Control": "no-store"})

    async def open_folder(request):
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError()
        case = evidence_case(payload.get("case"))
        if engine.state["busy"]:
            return web.json_response({"error": "Wait for the job to finish or cancel and finalize it first."}, status=409)
        try:
            await open_evidence_folder(case)
        except (OSError, TimeoutError):
            return web.json_response({"error": f"Could not open a file manager. Open this folder manually: {case}"}, status=503)
        return web.json_response({"ok": True, "path": str(case)})

    async def delete_result(request):
        payload = await request.json()
        if not isinstance(payload, dict) or payload.get("confirmed") is not True:
            raise ValueError()
        if engine.state["busy"]:
            return web.json_response({"error": "Wait for the job to finish first."}, status=409)
        case = evidence_case(payload.get("case"))
        shutil.rmtree(case)
        return web.json_response({"ok": True})

    async def clear_history(request):
        payload = await request.json()
        if not isinstance(payload, dict) or payload.get("confirmed") is not True:
            raise ValueError()
        if engine.state["busy"]:
            return web.json_response({"error": "Wait for the job to finish first."}, status=409)
        root = evidence_root()
        root.mkdir(parents=True, exist_ok=True)
        names = []
        for path in root.glob("EVIDEX_*"):
            try:
                names.append(evidence_case(path.name).name)
            except ValueError:
                continue
        write_json(root / ".hidden_history.json", {"cases": names})
        return web.json_response({"ok": True})

    async def stylesheet(request):
        return web.FileResponse(Path(__file__).with_suffix(".css"), headers={"Content-Type": "text/css", "Cache-Control": "no-store"})

    async def guide_asset(request):
        name = request.match_info["name"]
        if not re.fullmatch(r"0[1-6]-[a-z-]+\.webp", name):
            raise web.HTTPNotFound()
        asset = Path(__file__).with_name("guide_assets") / name
        if not asset.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(asset, headers={"Content-Type": "image/webp", "Cache-Control": "public, max-age=3600"})

    async def messages(request):
        case = evidence_case(request.query.get("case"))
        offset = int(request.query.get("offset", "0"))
        if offset < 0 or offset > 1_000_000:
            raise ValueError()
        query = request.query.get("q", "").casefold()[:200]
        records, matched, more = [], 0, False
        path = case / "messages.jsonl"
        if path.resolve().parent != case or not path.is_file():
            raise web.HTTPNotFound()
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict) or query not in str(record.get("text", "")).casefold():
                    continue
                if matched >= offset:
                    if len(records) == 50:
                        more = True
                        break
                    # Only evidence fields; no account/session configuration.
                    records.append({key: record.get(key) for key in ("message_id", "sender_id", "date_utc", "text", "media")})
                matched += 1
        return web.json_response({"messages": records, "offset": offset, "more": more}, headers={"Cache-Control": "no-store"})

    async def attachment(request):
        case = evidence_case(request.query.get("case"))
        relative = request.query.get("path", "")
        path = (case / relative).resolve()
        media = (case / "media").resolve()
        if media.parent != case or not path.is_relative_to(media) or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

    async def cleanup(app):
        await engine.close()

    app.router.add_get("/", index)
    app.router.add_get("/app.css", stylesheet)
    app.router.add_get("/api/state", state)
    app.router.add_post("/api/run", run)
    app.router.add_post("/api/answer", answer)
    app.router.add_post("/api/cancel", cancel)
    app.router.add_get("/guide-assets/{name}", guide_asset)
    app.router.add_get("/api/messages", messages)
    app.router.add_get("/api/attachment", attachment)
    app.router.add_get("/api/results", results)
    app.router.add_post("/api/open-folder", open_folder)
    app.router.add_post("/api/delete-result", delete_result)
    app.router.add_post("/api/clear-history", clear_history)
    app.on_cleanup.append(cleanup)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    print(f"EVIDEX Next {VERSION} · http://127.0.0.1:{args.port} · Ctrl+C to stop")
    web.run_app(create_app(), host="127.0.0.1", port=args.port, access_log=None, print=None)


if __name__ == "__main__":
    main()
