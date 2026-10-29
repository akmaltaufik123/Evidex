"""Telegram transport lifecycle shared by the TUI, browser and connection check."""
from __future__ import annotations

import asyncio
import os
import ssl
import time
from pathlib import Path
from typing import Any, Callable

from telethon import TelegramClient
from telethon.errors import ApiIdInvalidError
from telethon.network.connection import ConnectionTcpFull, ConnectionTcpObfuscated, ConnectionHttp
from telethon.sessions import StringSession

SOCKET_TIMEOUT_SECONDS = 10
TRANSPORT_TIMEOUT_SECONDS = 15
EXISTING_SESSION_TIMEOUT_SECONDS = 60
CLEANUP_TIMEOUT_SECONDS = 3
TELEGRAM_TRANSPORTS = (
    ("standard MTProto", ConnectionTcpFull),
    ("obfuscated MTProto", ConnectionTcpObfuscated),
    ("HTTP MTProto", ConnectionHttp),
)


def connection_error_detail(error: Exception) -> str:
    """Describe network failures without copying credential-bearing exception text."""
    # Third-party/proxy exceptions may embed URLs, credentials or request data.
    # Use fixed descriptions rather than attempting to redact arbitrary text.
    if isinstance(error, TimeoutError):
        message = "connection timed out (socket or attempt deadline)"
    elif isinstance(error, ConnectionResetError):
        message = "connection reset by peer"
    elif isinstance(error, ConnectionRefusedError):
        message = "connection refused"
    elif isinstance(error, ssl.SSLError):
        message = "TLS negotiation failed"
        if error.reason == "WRONG_VERSION_NUMBER":
            message += " (WRONG_VERSION_NUMBER)"
    elif isinstance(error, ConnectionError):
        message = "transport connection failed"
    elif isinstance(error, OSError):
        message = "network or session I/O failure"
        if isinstance(error.errno, int):
            message += f" (errno={error.errno})"
    else:
        message = "connection failed; exception text withheld for credential safety"
    return f"{type(error).__name__}: {message}"


def session_file_path(session: Path) -> Path:
    value = str(session)
    return Path(value if value.endswith(".session") else value + ".session")


def connection_timeout(existing: bool) -> float:
    value = os.getenv("EVIDEX_CONNECT_TIMEOUT")
    if value is None:
        return EXISTING_SESSION_TIMEOUT_SECONDS if existing else TRANSPORT_TIMEOUT_SECONDS
    try:
        timeout = float(value)
    except ValueError:
        raise ValueError("EVIDEX_CONNECT_TIMEOUT must be a finite number between 1 and 300") from None
    if not 1 <= timeout <= 300:
        raise ValueError("EVIDEX_CONNECT_TIMEOUT must be a finite number between 1 and 300")
    return timeout


async def disconnect_client(client: TelegramClient, log: Callable[[str], None]) -> None:
    try:
        await asyncio.wait_for(client.disconnect(), timeout=CLEANUP_TIMEOUT_SECONDS)
    except Exception as error:
        log(f"Cleanup: {connection_error_detail(error)}")


async def connect_client(
    api_id: int, api_hash: str, session: Path | StringSession, *,
    proxy: dict[str, Any] | None = None,
    log: Callable[[str], None] = print,
    status: Callable[[str], None] = lambda message: None,
    active: Callable[[TelegramClient | None], None] = lambda client: None,
) -> TelegramClient:
    """Connect only; the caller owns authorization and successful-client cleanup.

    No session substitution, account switching, UI calls or background threads.
    Retries and socket timeout match the operator's successful standalone test.
    """
    existing = isinstance(session, Path) and session_file_path(session).is_file()
    budget = connection_timeout(existing)
    log(f"Connection: {'saved' if existing else 'new'} session; "
        f"{'explicit proxy' if proxy else 'direct (no proxy)'}; "
        f"socket={SOCKET_TIMEOUT_SECONDS}s, budget={budget}s, retries=1.")
    failures: list[str] = []
    for name, transport in TELEGRAM_TRANSPORTS:
        candidate = None
        connected = False
        started = time.monotonic()
        try:
            # Constructor errors (including SQLite failures) belong to this attempt.
            candidate = TelegramClient(
                str(session) if isinstance(session, Path) else session,
                api_id, api_hash, connection=transport, proxy=proxy,
                timeout=SOCKET_TIMEOUT_SECONDS, request_retries=1,
                connection_retries=1, retry_delay=1,
            )
            active(candidate)
            status(f"Connecting via {name}…")
            log(f"Trying {name}: dc={candidate.session.dc_id}, port={candidate.session.port}.")
            await asyncio.wait_for(candidate.connect(), timeout=budget)
            if not candidate.is_connected():
                raise ConnectionError("transport did not connect")
            connected = True
            log(f"Transport connected via {name}; account authorization pending.")
            return candidate
        except (asyncio.CancelledError, ApiIdInvalidError):
            raise
        except (OSError, ConnectionError) as error:
            detail = f"{name}: {connection_error_detail(error)} (elapsed={time.monotonic() - started:.1f}s)"
            failures.append(detail)
            log(detail)
        finally:
            if not connected:
                try:
                    if candidate is not None:
                        await disconnect_client(candidate, log)
                finally:
                    active(None)
    raise ConnectionError("All Telegram transports failed. " + "; ".join(failures))


async def check_connection(api_id: int, api_hash: str) -> None:
    """Explicit fresh/direct transport check, never logs in or touches saved sessions."""
    print("Fresh in-memory session; direct connection; no account login or evidence acquisition.")
    client = await connect_client(api_id, api_hash, StringSession())
    try:
        print("PASS: transport connected. Account authorization has NOT been tested.")
    finally:
        await disconnect_client(client, print)
