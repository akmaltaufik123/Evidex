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
- Automatic standard, obfuscated, and HTTP MTProto Telegram transport fallback
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

### Run in a localhost browser

Install the optional browser dependency in the same virtual environment:

```bash
python3 -m pip install -r requirements-web.txt
python3 evidex.py --web
```

Open <http://127.0.0.1:8000> in your browser. To choose another port, use
`python3 evidex.py --web --port 8080`. The server binds to the local machine only.
This runs the existing Textual interface through
[Textual Serve](https://github.com/Textualize/textual-serve), with the same
Telegram prompts, proxy settings and evidence exports. Telegram still connects
from the Python process; browser mode does not bypass network connection failures.

Use one browser tab at a time and close any terminal instance using the same
Telegram session. Each browser connection starts its own app process. Keep the
server terminal open. Cancel an active acquisition with the on-screen Cancel
button and wait for finalization before closing or refreshing the tab. Stop the
server with Ctrl+C after acquisition has finished. Files remain on the machine
running Python, in the same working-directory-relative locations as terminal mode.
Browser shortcuts may intercept function/control keys; use the on-screen buttons
when needed. The terminal launch command remains `python3 evidex.py`.

Get an API ID and API hash from Telegram's official developer portal: <https://my.telegram.org/>.

Credentials can be entered in the TUI or prefilled for the current process:

```bash
export TELEGRAM_API_ID="your_api_id"
export TELEGRAM_API_HASH="your_api_hash"
export TELEGRAM_PHONE="+60123456789"
python3 evidex.py
```

### Connection check and architecture

The terminal and browser use the same `telegram_connection.py` connector:
connect transport, authorize account, acquire evidence, finalize hashes, disconnect.
No UI or threading logic lives in the connector. All transports use a 10-second
socket timeout and one retry. New sessions have a 15-second attempt budget,
matching the successful standalone diagnostic setup; saved session files have
60 seconds. A saved managed session receives the same policy as a selected file.
To override the attempt budget for either, set `EVIDEX_CONNECT_TIMEOUT` to a
number of seconds between 1 and 300.

To isolate Telegram connectivity from the interface and persistent sessions:

```bash
python3 evidex.py --check-connection
```

Enter the API ID and masked API hash when prompted, or use their existing
environment variables. This is an explicit fresh, direct, in-memory transport
test. It ignores proxy and saved-session settings, never logs in, never requests
a verification code, and never opens or replaces saved sessions. A pass proves
transport connectivity only. If it passes while extraction fails, compare the
explicit proxy and saved-session DC/port shown in the extraction log. Do not
delete session files to test connectivity.

### Filtered Telegram connections

If direct Telegram handshakes are filtered, enter a trusted proxy in the masked
**Proxy URL** field:

```text
socks5://username:password@proxy-host:port
http://username:password@proxy-host:port
```

The proxy can also be provided explicitly with `EVIDEX_PROXY_URL`.
Connections are direct by default; generic `ALL_PROXY` settings are not inherited. Proxy credentials are never written to evidence artifacts.
Avoid untrusted public proxies because they can observe connection metadata.

### Reusing an existing CLI session

If another Telethon CLI already connects successfully, enter the absolute path
to its `.session` file in **Existing Telegram session**. EVIDEX will reuse its
authorized key and Telegram data-center assignment instead of forcing a new key
exchange. Close the other CLI before starting EVIDEX; the same SQLite session
must not be opened by two processes simultaneously.

Select a session explicitly in the form or through `EVIDEX_SESSION_PATH`.
EVIDEX does not automatically select unrelated session files.

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
