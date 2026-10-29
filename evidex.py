"""EVIDEX: a terminal UI for authorized Telegram evidence extraction."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.network.connection import (
    ConnectionHttp,
    ConnectionTcpFull,
    ConnectionTcpObfuscated,
)
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    Log,
    ProgressBar,
    Static,
)

__version__ = "2.1.1"
APP_NAME = "EVIDEX"
APP_SUBTITLE = "Evidence Extraction Tool"
TRANSPORT_TIMEOUT_SECONDS = 8
EXISTING_SESSION_TIMEOUT_SECONDS = 60
TELEGRAM_TRANSPORTS = (
    ("standard MTProto", ConnectionTcpFull),
    ("obfuscated MTProto", ConnectionTcpObfuscated),
    ("HTTPS", ConnectionHttp),
)
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_EXPORT_DIR = Path(os.getenv("EVIDEX_EXPORT_DIR", "evidence_exports"))
SESSION_DIR = Path(os.getenv("EVIDEX_SESSION_DIR", ".evidex_sessions"))
ABOUT_TEXT = """EVIDEX: Evidence Extraction Tool

Developer: Akmal Taufik
Email: work.akmaltaufik@gmail.com
LinkedIn: https://www.linkedin.com/in/akmaltaufik
TikTok: @mohammadakmaltaufik
"""


@dataclass(frozen=True)
class ExtractionConfig:
    """Validated settings captured from the extraction form."""

    api_id: int
    api_hash: str
    phone: str
    target: str
    case_id: str
    output_root: Path
    message_limit: int | None
    download_media: bool
    proxy: dict[str, Any] | None
    session_path: Path | None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_name(value: str, fallback: str = "case") -> str:
    """Convert user-controlled text to a safe, short directory component."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    return (cleaned[:80] or fallback)


def parse_proxy_url(value: str) -> dict[str, Any]:
    """Parse a SOCKS/HTTP proxy URL into Telethon's proxy configuration."""
    parsed = urlparse(value.strip())
    proxy_type = parsed.scheme.lower()
    if proxy_type not in {"socks5", "socks4", "http"}:
        raise ValueError("Proxy scheme must be socks5, socks4, or http.")
    if not parsed.hostname:
        raise ValueError("Proxy URL must include a host.")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Proxy URL contains an invalid port.") from error
    if port is None:
        raise ValueError("Proxy URL must include a port.")

    return {
        "proxy_type": proxy_type,
        "addr": parsed.hostname,
        "port": port,
        "username": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "rdns": True,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically so interrupted runs do not leave partial metadata."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_project_text(filename: str) -> str:
    path = BASE_DIR / filename
    if not path.is_file():
        return f"Document not found: {filename}"
    return path.read_text(encoding="utf-8")


def discover_local_session() -> str:
    """Prefill one unambiguous local Telethon session for easy migration."""
    candidates: set[Path] = set()
    for directory in {Path.cwd().resolve(), BASE_DIR}:
        candidates.update(path.resolve() for path in directory.glob("*.session"))
    return str(next(iter(candidates))) if len(candidates) == 1 else ""


class PromptScreen(ModalScreen[str | None]):
    """Modal input used for Telegram verification and two-factor auth."""

    CSS = """
    PromptScreen {
        align: center middle;
        background: rgba(3, 10, 18, 0.78);
    }
    #prompt-dialog {
        width: 62;
        height: auto;
        padding: 1 2;
        border: tall #2dd4bf;
        background: #0b1623;
    }
    #prompt-title {
        color: #e6edf3;
        text-style: bold;
        margin-bottom: 1;
    }
    #prompt-help { color: #94a3b8; margin-bottom: 1; }
    #prompt-actions { height: auto; margin-top: 1; align-horizontal: right; }
    #prompt-actions Button { margin-left: 1; }
    """

    def __init__(
        self,
        title: str,
        help_text: str,
        *,
        password: bool = False,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.help_text = help_text
        self.password = password

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-dialog"):
            yield Label(self.title_text, id="prompt-title")
            yield Label(self.help_text, id="prompt-help")
            yield Input(password=self.password, id="prompt-value")
            with Horizontal(id="prompt-actions"):
                yield Button("Cancel", variant="default", id="prompt-cancel")
                yield Button("Continue", variant="primary", id="prompt-submit")

    def on_mount(self) -> None:
        self.query_one("#prompt-value", Input).focus()

    @on(Input.Submitted, "#prompt-value")
    def submit_input(self) -> None:
        self.submit_value()

    @on(Button.Pressed, "#prompt-submit")
    def submit_button(self) -> None:
        self.submit_value()

    @on(Button.Pressed, "#prompt-cancel")
    def cancel(self) -> None:
        self.dismiss(None)

    def submit_value(self) -> None:
        value = self.query_one("#prompt-value", Input).value.strip()
        if not value:
            self.notify("A value is required.", severity="warning")
            return
        self.dismiss(value)


class DocumentScreen(ModalScreen[None]):
    """Scrollable in-app viewer for bundled guidance documents."""

    BINDINGS = [Binding("escape", "close", "Close")]
    CSS = """
    DocumentScreen {
        align: center middle;
        background: rgba(3, 10, 18, 0.82);
    }
    #document-dialog {
        width: 90%;
        height: 90%;
        border: tall #2dd4bf;
        background: #0b1623;
    }
    #document-title {
        height: 3;
        padding: 1 2 0 2;
        color: #2dd4bf;
        text-style: bold;
    }
    #document-scroll { height: 1fr; padding: 0 2; }
    #document-close { dock: bottom; width: 100%; }
    """

    def __init__(self, title: str, content: str) -> None:
        super().__init__()
        self.document_title = title
        self.document_content = content

    def compose(self) -> ComposeResult:
        with Vertical(id="document-dialog"):
            yield Label(self.document_title, id="document-title")
            with VerticalScroll(id="document-scroll"):
                yield Static(self.document_content)
            yield Button("Close  [Esc]", id="document-close")

    @on(Button.Pressed, "#document-close")
    def close_button(self) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class EvidexApp(App[None]):
    """Interactive terminal application for reproducible evidence exports."""

    TITLE = f"{APP_NAME} — {APP_SUBTITLE}"
    SUB_TITLE = f"v{__version__}"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+r", "focus_start", "Run extraction"),
        Binding("ctrl+x", "cancel_extraction", "Cancel"),
        Binding("f1", "legal", "Legal"),
        Binding("f2", "setup", "Setup"),
        Binding("f3", "about", "About"),
        Binding("ctrl+q", "request_quit", "Quit", show=True),
    ]

    CSS = """
    Screen {
        background: #07111d;
        color: #d8e2ec;
    }
    Header {
        background: #0b1623;
        color: #2dd4bf;
    }
    Footer { background: #0b1623; }
    #brand {
        height: 5;
        padding: 1 2;
        background: #0d1b2a;
        border-bottom: solid #1e3a4f;
    }
    #brand-title {
        color: #2dd4bf;
        text-style: bold;
    }
    #brand-subtitle { color: #94a3b8; }
    #workspace {
        height: 1fr;
        padding: 1 2;
    }
    #form-panel {
        width: 48;
        min-width: 40;
        height: 100%;
        padding: 1 2;
        border: round #1e3a4f;
        background: #0b1623;
        overflow-y: auto;
    }
    #activity-panel {
        width: 1fr;
        height: 100%;
        margin-left: 1;
        padding: 1;
        border: round #1e3a4f;
        background: #091520;
    }
    .section-title {
        color: #2dd4bf;
        text-style: bold;
        margin-bottom: 1;
    }
    .field-label { color: #a8b7c7; margin-top: 1; }
    Input {
        border: tall #334155;
        background: #07111d;
    }
    Input:focus { border: tall #2dd4bf; }
    #legal-accept { margin-top: 1; }
    #actions { height: 3; margin-top: 1; }
    #actions Button { width: 1fr; margin-right: 1; }
    #doc-actions { height: 3; margin-top: 1; }
    #doc-actions Button { width: 1fr; margin-right: 1; }
    #activity-heading { height: 2; color: #2dd4bf; text-style: bold; }
    #status-line { height: 2; color: #94a3b8; }
    #progress { height: 2; margin-bottom: 1; }
    #event-log {
        height: 1fr;
        border: tall #172b3d;
        background: #050d16;
        color: #c8d5e2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._extraction_worker: Any | None = None
        self._active_client: TelegramClient | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="brand"):
            yield Static("E V I D E X", id="brand-title")
            yield Static(
                "Evidence Extraction Tool  ·  Telegram acquisition with integrity manifests",
                id="brand-subtitle",
            )
        with Horizontal(id="workspace"):
            with VerticalScroll(id="form-panel"):
                yield Label("EXTRACTION PROFILE", classes="section-title")
                yield Label("Telegram API ID", classes="field-label")
                yield Input(
                    value=os.getenv("TELEGRAM_API_ID", ""),
                    placeholder="Numeric API ID",
                    id="api-id",
                )
                yield Label("Telegram API hash", classes="field-label")
                yield Input(
                    value=os.getenv("TELEGRAM_API_HASH", ""),
                    placeholder="API hash (not written to evidence logs)",
                    password=True,
                    id="api-hash",
                )
                yield Label("Account phone", classes="field-label")
                yield Input(
                    value=os.getenv("TELEGRAM_PHONE", ""),
                    placeholder="International format, e.g. +60123456789",
                    id="phone",
                )
                yield Label("Target", classes="field-label")
                yield Input(
                    placeholder="@username, public link, or numeric ID",
                    id="target",
                )
                yield Label("Proxy URL (optional, masked)", classes="field-label")
                yield Input(
                    value=os.getenv(
                        "EVIDEX_PROXY_URL",
                        os.getenv("ALL_PROXY", ""),
                    ),
                    placeholder="socks5://host:port or http://host:port",
                    password=True,
                    id="proxy-url",
                )
                yield Label("Existing Telegram session (optional)", classes="field-label")
                yield Input(
                    value=os.getenv("EVIDEX_SESSION_PATH", discover_local_session()),
                    placeholder="Path to an existing .session file",
                    id="session-path",
                )
                yield Label("Case / reference ID", classes="field-label")
                yield Input(
                    value=f"case-{utc_now():%Y%m%d}",
                    placeholder="Used in the evidence folder name",
                    id="case-id",
                )
                yield Label("Export directory", classes="field-label")
                yield Input(value=str(DEFAULT_EXPORT_DIR), id="output-root")
                yield Label("Maximum messages (blank = all)", classes="field-label")
                yield Input(placeholder="All messages", id="message-limit")
                yield Checkbox("Download message media", value=True, id="download-media")
                yield Checkbox(
                    "I confirm I am authorized to collect this data",
                    value=False,
                    id="legal-accept",
                )
                with Horizontal(id="actions"):
                    yield Button("Start extraction", variant="primary", id="start")
                    yield Button("Cancel", variant="error", id="cancel", disabled=True)
                with Horizontal(id="doc-actions"):
                    yield Button("Legal  [F1]", id="legal")
                    yield Button("Setup  [F2]", id="setup")
                    yield Button("About  [F3]", id="about")
            with Vertical(id="activity-panel"):
                yield Label("ACQUISITION ACTIVITY", id="activity-heading")
                yield Label("Ready. Configure an authorized extraction.", id="status-line")
                yield ProgressBar(total=100, show_eta=False, id="progress")
                yield Log(highlight=True, auto_scroll=True, max_lines=2000, id="event-log")
        yield Footer()

    def log_event(self, message: str) -> None:
        timestamp = utc_now().strftime("%H:%M:%S")
        self.query_one("#event-log", Log).write_line(f"[{timestamp} UTC] {message}")

    def set_status(self, message: str) -> None:
        self.query_one("#status-line", Label).update(message)

    def set_running(self, running: bool) -> None:
        self.query_one("#start", Button).disabled = running
        self.query_one("#cancel", Button).disabled = not running

    def collect_config(self) -> ExtractionConfig | None:
        api_id_text = self.query_one("#api-id", Input).value.strip()
        api_hash = self.query_one("#api-hash", Input).value.strip()
        phone = self.query_one("#phone", Input).value.strip()
        target = self.query_one("#target", Input).value.strip()
        proxy_text = self.query_one("#proxy-url", Input).value.strip()
        session_text = self.query_one("#session-path", Input).value.strip()
        case_id = self.query_one("#case-id", Input).value.strip()
        output_text = self.query_one("#output-root", Input).value.strip()
        limit_text = self.query_one("#message-limit", Input).value.strip()
        authorized = self.query_one("#legal-accept", Checkbox).value

        if not api_id_text.isdigit() or int(api_id_text) <= 0:
            self.notify("Telegram API ID must be a positive number.", severity="error")
            return None
        if not api_hash:
            self.notify("Telegram API hash is required.", severity="error")
            return None
        if not phone:
            self.notify("Account phone number is required.", severity="error")
            return None
        if not target:
            self.notify("A Telegram target is required.", severity="error")
            return None
        if not case_id:
            self.notify("A case or reference ID is required.", severity="error")
            return None
        if not output_text:
            self.notify("An export directory is required.", severity="error")
            return None
        if limit_text and (not limit_text.isdigit() or int(limit_text) <= 0):
            self.notify("Maximum messages must be a positive number.", severity="error")
            return None
        if not authorized:
            self.notify("Authorization confirmation is required.", severity="error")
            return None

        proxy: dict[str, Any] | None = None
        if proxy_text:
            try:
                proxy = parse_proxy_url(proxy_text)
            except ValueError as error:
                self.notify(str(error), severity="error")
                return None

        session_path: Path | None = None
        if session_text:
            session_path = Path(session_text).expanduser().resolve()
            if not session_path.is_file():
                self.notify(
                    "The selected Telegram session file does not exist.",
                    severity="error",
                )
                return None
            if session_path.suffix != ".session":
                self.notify(
                    "Telegram session files must use the .session extension.",
                    severity="error",
                )
                return None

        return ExtractionConfig(
            api_id=int(api_id_text),
            api_hash=api_hash,
            phone=phone,
            target=target,
            case_id=safe_name(case_id),
            output_root=Path(output_text).expanduser().resolve(),
            message_limit=int(limit_text) if limit_text else None,
            download_media=self.query_one("#download-media", Checkbox).value,
            proxy=proxy,
            session_path=session_path,
        )

    @on(Button.Pressed, "#start")
    def start_button(self) -> None:
        config = self.collect_config()
        if config is None:
            return
        self._extraction_worker = self.run_extraction(config)

    @on(Button.Pressed, "#cancel")
    def cancel_button(self) -> None:
        self.action_cancel_extraction()

    @on(Button.Pressed, "#legal")
    def legal_button(self) -> None:
        self.action_legal()

    @on(Button.Pressed, "#setup")
    def setup_button(self) -> None:
        self.action_setup()

    @on(Button.Pressed, "#about")
    def about_button(self) -> None:
        self.action_about()

    def action_focus_start(self) -> None:
        self.query_one("#start", Button).focus()

    def action_cancel_extraction(self) -> None:
        if self._extraction_worker is not None:
            self._extraction_worker.cancel()
            self.log_event("Cancellation requested; finalizing the partial acquisition.")

    def action_request_quit(self) -> None:
        if self._extraction_worker is not None:
            self.notify(
                "Cancel the active extraction and wait for finalization before quitting.",
                severity="warning",
            )
            return
        self.exit()

    def action_legal(self) -> None:
        self.push_screen(
            DocumentScreen(
                "Legal & Responsible Use",
                read_project_text("README_LEGAL.txt"),
            )
        )

    def action_setup(self) -> None:
        self.push_screen(
            DocumentScreen(
                "Installation & Telegram Setup",
                read_project_text("README_INSTALL.txt"),
            )
        )

    def action_about(self) -> None:
        self.push_screen(DocumentScreen("About EVIDEX", ABOUT_TEXT))

    @work(exclusive=True, group="extract")
    async def run_extraction(self, config: ExtractionConfig) -> None:
        """Authenticate, collect messages, and finalize integrity artifacts."""
        client: TelegramClient | None = None
        case_dir: Path | None = None
        metadata: dict[str, Any] = {}
        message_count = 0
        media_count = 0
        media_errors = 0
        run_status = "failed"
        failure: str | None = None
        started_at = utc_now()

        self.set_running(True)
        self.query_one("#progress", ProgressBar).update(total=100, progress=0)
        self.set_status("Connecting to Telegram…")
        self.log_event("Starting authenticated Telegram session.")

        try:
            config.output_root.mkdir(parents=True, exist_ok=True)
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            session_key = hashlib.sha256(config.phone.encode("utf-8")).hexdigest()[:12]
            session_path = config.session_path or SESSION_DIR / f"evidex_{session_key}"
            if config.session_path:
                self.log_event("Using the operator-selected existing Telegram session.")
            else:
                self.log_event("Using an EVIDEX-managed Telegram session.")
            client = await self.connect_telegram(config, session_path)
            await self.authorize_client(client, config.phone)

            target: str | int = config.target
            if config.target.lstrip("-").isdigit():
                target = int(config.target)

            self.set_status("Resolving target…")
            entity = await client.get_entity(target)
            entity_name = (
                getattr(entity, "title", None)
                or getattr(entity, "username", None)
                or str(getattr(entity, "id", config.target))
            )

            timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
            folder_stem = f"EVIDEX_{config.case_id}_{timestamp}"
            case_dir = config.output_root / folder_stem
            suffix = 1
            while case_dir.exists():
                case_dir = config.output_root / f"{folder_stem}_{suffix}"
                suffix += 1
            case_dir.mkdir(parents=False)
            media_dir = case_dir / "media"
            if config.download_media:
                media_dir.mkdir()

            total_result = await client.get_messages(entity, limit=0)
            available_messages = int(getattr(total_result, "total", 0) or 0)
            expected_messages = (
                min(available_messages, config.message_limit)
                if config.message_limit is not None
                else available_messages
            )
            self.query_one("#progress", ProgressBar).update(
                total=max(expected_messages, 1), progress=0
            )

            metadata = {
                "tool": APP_NAME,
                "tool_version": __version__,
                "purpose": APP_SUBTITLE,
                "case_id": config.case_id,
                "acquisition_started_utc": started_at.isoformat(),
                "acquisition_status": "running",
                "source": {
                    "platform": "Telegram",
                    "requested_target": config.target,
                    "resolved_name": entity_name,
                    "entity_id": getattr(entity, "id", None),
                },
                "settings": {
                    "message_limit": config.message_limit,
                    "download_media": config.download_media,
                    "ordering": "oldest_to_newest",
                    "proxy_used": config.proxy is not None,
                    "existing_session_reused": config.session_path is not None,
                },
                "available_messages_at_start": available_messages,
                "credential_storage": "Credentials were not written to this export.",
            }
            write_json(case_dir / "metadata.json", metadata)
            self.log_event(f"Resolved target: {entity_name}")
            self.log_event(f"Evidence directory: {case_dir}")
            self.set_status(f"Extracting from {entity_name}…")

            jsonl_path = case_dir / "messages.jsonl"
            text_path = case_dir / "messages.txt"
            with (
                jsonl_path.open("w", encoding="utf-8", newline="\n") as jsonl_file,
                text_path.open("w", encoding="utf-8", newline="\n") as text_file,
            ):
                async for message in client.iter_messages(
                    entity,
                    limit=config.message_limit,
                    reverse=True,
                ):
                    media_info: dict[str, Any] | None = None
                    if message.media is not None:
                        media_info = {
                            "telegram_type": type(message.media).__name__,
                            "name": getattr(message.file, "name", None),
                            "mime_type": getattr(message.file, "mime_type", None),
                            "size_bytes": getattr(message.file, "size", None),
                        }
                        if config.download_media:
                            try:
                                downloaded = await client.download_media(
                                    message,
                                    file=str(media_dir),
                                )
                                if downloaded:
                                    downloaded_path = Path(downloaded).resolve()
                                    relative_path = downloaded_path.relative_to(
                                        case_dir.resolve()
                                    )
                                    media_info.update(
                                        {
                                            "saved_path": relative_path.as_posix(),
                                            "sha256": sha256_file(downloaded_path),
                                        }
                                    )
                                    media_count += 1
                            # Preserve the message record even if its attachment fails.
                            except Exception as media_error:
                                media_errors += 1
                                media_info["download_error"] = type(media_error).__name__
                                self.log_event(
                                    f"Media download failed for message {message.id}: "
                                    f"{type(media_error).__name__}"
                                )

                    message_date = message.date
                    if message_date is not None and message_date.tzinfo is None:
                        message_date = message_date.replace(tzinfo=timezone.utc)
                    edit_date = message.edit_date
                    if edit_date is not None and edit_date.tzinfo is None:
                        edit_date = edit_date.replace(tzinfo=timezone.utc)

                    record = {
                        "message_id": message.id,
                        "date_utc": message_date.astimezone(timezone.utc).isoformat()
                        if message_date
                        else None,
                        "edit_date_utc": edit_date.astimezone(timezone.utc).isoformat()
                        if edit_date
                        else None,
                        "sender_id": message.sender_id,
                        "post_author": message.post_author,
                        "text": message.raw_text or "",
                        "reply_to_message_id": message.reply_to_msg_id,
                        "grouped_id": message.grouped_id,
                        "views": message.views,
                        "forwards": message.forwards,
                        "replies": getattr(message.replies, "replies", None),
                        "media": media_info,
                    }
                    jsonl_file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                    text_file.write(
                        f"[{record['date_utc'] or 'unknown time'}] "
                        f"message={message.id} sender={message.sender_id}\n"
                    )
                    text_file.write((message.raw_text or "[No text / media message]") + "\n")
                    if media_info and media_info.get("saved_path"):
                        text_file.write(f"[Media] {media_info['saved_path']}\n")
                    text_file.write("-" * 72 + "\n")

                    message_count += 1
                    self.query_one("#progress", ProgressBar).advance(1)
                    preview = (message.raw_text or "[media/no text]").replace("\n", " ")[:100]
                    self.log_event(f"#{message.id} · sender {message.sender_id} · {preview}")

            run_status = "complete"
            self.set_status(f"Complete — {message_count} messages acquired.")
            self.notify("Evidence extraction completed.", severity="information")

        except asyncio.CancelledError:
            run_status = "cancelled"
            failure = "Cancelled by operator"
            self.set_status(f"Cancelled — {message_count} messages preserved.")
            self.notify(
                "Extraction cancelled; partial evidence was finalized.",
                severity="warning",
            )
        except ApiIdInvalidError:
            failure = "Telegram rejected the API ID or API hash."
            self.report_failure(failure)
        except PhoneCodeInvalidError:
            failure = "The Telegram verification code was invalid."
            self.report_failure(failure)
        except PasswordHashInvalidError:
            failure = "The Telegram two-factor password was invalid."
            self.report_failure(failure)
        except FloodWaitError as error:
            failure = f"Telegram rate limit: retry after {error.seconds} seconds."
            self.report_failure(failure)
        except TimeoutError as error:
            failure = (
                f"{error} "
                "Check internet access, VPN/firewall settings, and Telegram access "
                "from this terminal environment."
            )
            self.report_failure(failure)
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"
            self.report_failure(failure)
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            self._active_client = None

            if case_dir is not None and case_dir.exists():
                finished_at = utc_now()
                metadata.update(
                    {
                        "acquisition_finished_utc": finished_at.isoformat(),
                        "acquisition_status": run_status,
                        "result": {
                            "messages_acquired": message_count,
                            "media_files_acquired": media_count,
                            "media_download_errors": media_errors,
                            "failure": failure,
                        },
                    }
                )
                write_json(case_dir / "metadata.json", metadata)
                report = {
                    "case_id": config.case_id,
                    "status": run_status,
                    "started_utc": started_at.isoformat(),
                    "finished_utc": finished_at.isoformat(),
                    "messages_acquired": message_count,
                    "media_files_acquired": media_count,
                    "media_download_errors": media_errors,
                    "failure": failure,
                }
                write_json(case_dir / "acquisition_report.json", report)
                self.write_manifest(case_dir)
                self.log_event(
                    f"Integrity manifest finalized: {case_dir / 'manifest.sha256'}"
                )

            self.set_running(False)
            self._extraction_worker = None

    async def connect_telegram(
        self,
        config: ExtractionConfig,
        session_path: Path,
    ) -> TelegramClient:
        """Try Telegram transports sequentially to handle protocol filtering."""
        failures: list[str] = []
        attempt_timeout = (
            EXISTING_SESSION_TIMEOUT_SECONDS
            if config.session_path is not None
            else TRANSPORT_TIMEOUT_SECONDS
        )
        connection_retries = 5 if config.session_path is not None else 1

        for transport_name, transport_class in TELEGRAM_TRANSPORTS:
            candidate = TelegramClient(
                str(session_path),
                config.api_id,
                config.api_hash,
                connection=transport_class,
                proxy=config.proxy,
                timeout=10 if config.session_path is not None else 6,
                request_retries=1,
                connection_retries=connection_retries,
                retry_delay=1,
            )
            connected = False
            self._active_client = candidate
            self.set_status(f"Connecting via {transport_name}…")
            self.log_event(
                f"Trying {transport_name} "
                f"({attempt_timeout}s timeout)"
                f"{' through configured proxy' if config.proxy else ''}."
            )

            try:
                await asyncio.wait_for(
                    candidate.connect(),
                    timeout=attempt_timeout,
                )
                if not candidate.is_connected():
                    raise ConnectionError("transport did not connect")
                connected = True
                self.log_event(f"Connected via {transport_name}.")
                return candidate
            except asyncio.CancelledError:
                raise
            except ApiIdInvalidError:
                raise
            except Exception as error:
                detail = f"{transport_name}: {type(error).__name__}"
                failures.append(detail)
                self.log_event(f"{detail}; trying the next transport.")
            finally:
                if not connected:
                    try:
                        await asyncio.wait_for(candidate.disconnect(), timeout=3)
                    except Exception:
                        pass

        self._active_client = None
        attempted = ", ".join(name for name, _ in TELEGRAM_TRANSPORTS)
        raise TimeoutError(
            f"All Telegram transports failed ({attempted}). "
            f"Diagnostics: {', '.join(failures)}."
        )

    async def authorize_client(self, client: TelegramClient, phone: str) -> None:
        """Complete Telegram login without ever falling back to blocking input()."""
        if await client.is_user_authorized():
            self.log_event("Existing authorized session loaded.")
            return

        self.set_status("Waiting for Telegram verification…")
        await client.send_code_request(phone)
        code = await self.push_screen_wait(
            PromptScreen(
                "Telegram verification",
                "Enter the code sent by Telegram. It is used only for this login.",
                password=True,
            )
        )
        if code is None:
            raise asyncio.CancelledError
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = await self.push_screen_wait(
                PromptScreen(
                    "Two-factor authentication",
                    "Enter your Telegram two-step verification password.",
                    password=True,
                )
            )
            if password is None:
                raise asyncio.CancelledError
            await client.sign_in(password=password)
        self.log_event("Telegram authorization successful.")

    def report_failure(self, message: str) -> None:
        self.set_status("Extraction failed. Review the activity log.")
        self.log_event(f"ERROR · {message}")
        self.notify(message, severity="error", timeout=8)

    def write_manifest(self, case_dir: Path) -> None:
        """Hash every completed evidence artifact using a portable manifest format."""
        manifest_path = case_dir / "manifest.sha256"
        entries: list[str] = []
        for path in sorted(case_dir.rglob("*")):
            if (
                path.is_file()
                and path != manifest_path
                and not path.name.endswith(".tmp")
            ):
                relative = path.relative_to(case_dir).as_posix()
                entries.append(f"{sha256_file(path)}  {relative}")
        temporary = manifest_path.with_suffix(".sha256.tmp")
        temporary.write_text("\n".join(entries) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(manifest_path)


def main() -> None:
    EvidexApp().run()


if __name__ == "__main__":
    main()
