# EVIDEX: Evidence Extraction Tool

EVIDEX is a terminal user interface for authorized Telegram evidence acquisition.

Built with [Textual](https://textual.textualize.io/) and [Telethon](https://docs.telethon.dev/), it uses an event-driven TUI instead of a numbered CLI menu.

> Use EVIDEX only where you have explicit authorization and a lawful basis to collect the data.

## Capabilities

- Guided extraction form with validation and masked secrets
- Telegram verification-code and two-factor prompts inside the TUI
- Full-history or message-limited acquisition in chronological order
- Optional media download with SHA-256 hashes
- Live acquisition log, progress, cancellation, and partial-run finalization
- Machine-readable JSONL plus human-readable text output
- Case metadata, acquisition report, and a portable SHA-256 manifest
- Credentials sourced at runtime or through environment variables—not source code
- Automatic standard, obfuscated, and HTTPS Telegram transport fallback
- Masked SOCKS5, SOCKS4, and HTTP proxy support for filtered networks
- Reuse of an existing authorized Telegram `.session` file

## Installation

EVIDEX requires Python 3.10 or newer.

```bash
git clone https://github.com/akmaltaufik123/Evidex.git
cd Evidex
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
python3 evidex.py
```

Get an API ID and API hash from Telegram's official developer portal: <https://my.telegram.org/>.

Credentials can be entered in the TUI or prefilled for the current process:

```bash
export TELEGRAM_API_ID="your_api_id"
export TELEGRAM_API_HASH="your_api_hash"
export TELEGRAM_PHONE="+60123456789"
python3 evidex.py
```

### Filtered Telegram connections

If direct Telegram handshakes are filtered, enter a trusted proxy in the masked
**Proxy URL** field:

```text
socks5://username:password@proxy-host:port
http://username:password@proxy-host:port
```

The proxy can also be provided for the current process with
`EVIDEX_PROXY_URL`. EVIDEX also recognizes `ALL_PROXY` when the dedicated
variable is unset. Proxy credentials are never written to evidence artifacts.
Avoid untrusted public proxies because they can observe connection metadata.

### Reusing an existing CLI session

If another Telethon CLI already connects successfully, enter the absolute path
to its `.session` file in **Existing Telegram session**. EVIDEX will reuse its
authorized key and Telegram data-center assignment instead of forcing a new key
exchange. Close the other CLI before starting EVIDEX; the same SQLite session
must not be opened by two processes simultaneously.

When exactly one `.session` file exists in the project or current directory,
EVIDEX automatically prefills it for review.

The session path may also be set with `EVIDEX_SESSION_PATH`. Treat `.session`
files as credentials and never commit or share them.

Do not commit credentials, session files, or evidence exports.

Run the local test suite with:

```bash
python3 -m unittest discover -s tests -v
```

## Controls

| Key | Action |
| --- | --- |
| `F1` | Open legal and responsible-use notice |
| `F2` | Open setup guide |
| `F3` | Open developer information |
| `Ctrl+R` | Focus the start button |
| `Ctrl+X` | Cancel and finalize a partial acquisition |
| `Ctrl+Q` | Quit |

## Evidence output

Each run creates a directory named `EVIDEX_<case>_<UTC timestamp>` containing:

| Artifact | Purpose |
| --- | --- |
| `metadata.json` | Tool, source, settings, timestamps, and final status |
| `messages.jsonl` | One structured JSON record per message |
| `messages.txt` | Human-readable chronological transcript |
| `media/` | Downloaded attachments, when enabled |
| `acquisition_report.json` | Counts, status, and non-secret error summary |
| `manifest.sha256` | SHA-256 digest for every completed artifact |

Verify an export from inside its directory with `sha256sum -c manifest.sha256` on systems that provide `sha256sum`.

## Security and legal

- API credentials and the account phone number are not written to evidence artifacts.
- Proxy addresses and credentials are not written to evidence artifacts.
- Telegram session files are stored under `.evidex_sessions/` and must be protected as credentials.
- A cancelled run is marked `cancelled`, and completed partial artifacts are hashed.
- Media download failures are recorded without aborting the message export.
- Review `README_LEGAL.txt` before use.

## Developer contact

- **Developer:** Akmal Taufik
- **Email:** work.akmaltaufik@gmail.com
- **LinkedIn:** https://www.linkedin.com/in/akmaltaufik
- **TikTok:** @mohammadakmaltaufik

## License

MIT. See `LICENSE`.
