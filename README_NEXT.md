# EVIDEX Next

A separate native localhost application. Launch with `python3 evidex_next.py`.
The existing `python3 evidex.py` application remains available.

## Clean setup

Use a new directory and virtual environment so changes in an old EVIDEX checkout
cannot block installation or run an older entry point:

```bash
git clone https://github.com/akmaltaufik123/Evidex.git ~/EvidexNext
cd ~/EvidexNext
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements-next.txt
python3 evidex_next.py
```

Open http://127.0.0.1:8000. For another port use `--port 8080`.
This entry point does not require Textual or Textual Serve.
If `~/EvidexNext` already exists, use a different new directory.

## Visual system (0.2.1)

EVIDEX now follows the user-supplied Hallmark design contract: Paper & Ink theme,
locked OKLCH/font tokens, a guided workbench and a separate saved-evidence shelf.
Both languages are checked at narrow mobile widths. The active guide uses new
content-only illustrations without fake device/browser frames; original images
are retained as archive assets. See [DESIGN.md](DESIGN.md) for the durable preview,
six-axis critique and validation record, and `AGENTS.md` for development rules.

## Languages and illustrated guidance (0.2.0)

Choose **Bahasa Melayu** or **English** at the top of the page. The interface,
five-step form, login prompts, completion notice and guide text switch languages
without clearing your form. Only the language preference is saved in browser
storage; API details and login credentials are not.

Open **Panduan bergambar / Illustrated guide** for six separate AI-generated
illustrations and readable instructions:

1. Sign in to the official my.telegram.org portal.
2. Obtain your own API ID and API hash in API development tools.
3. Test EVIDEX's direct connection (not account authorization).
4. Locate a public Telegram source link or username in its profile.
5. Complete the login you initiated, including two-factor verification if enabled.
6. Read the saved messages and preserve the original evidence files.

The images are illustrative, not actual screenshots or official Telegram assets.
All depicted codes and credentials are masked. Telegram's screens may differ.
Official sources are linked next to the relevant guide steps. See
[guide_assets/README.md](guide_assets/README.md) for the asset/prompt inventory.

The form now reveals one step at a time: connection, source, content, review,
and progress. Proxy/session options remain in advanced settings. The review does
not display your API hash. The server's existing authorization and acquisition
flow is unchanged.

## Workflow

1. Enter your Telegram API ID and API hash from https://my.telegram.org.
2. Select **Test direct connection**. This uses a fresh in-memory session,
   no proxy and no account login. A pass proves transport connectivity only.
3. Enter the account phone, target and case reference. Confirm authorization.
4. Select **Start acquisition**. Enter the Telegram code and two-factor password
   in the local page when requested. Already-authorized sessions skip login.
5. A green completion notice shows the saved message/media counts when the job
   has finished. The tab title also changes to “Extraction complete”. Select
   **Open evidence folder** to view JSONL, text, metadata, media, the acquisition
   report and SHA-256 manifest in your file manager.

**Saved evidence** lists up to 50 recent case folders, including jobs completed
before the server restarted. Select a case and open it without another extraction.
Use **Refresh results** to reload the list. **View messages / Lihat mesej** opens a
read-only searchable message viewer with 50 messages per page and attachment
downloads. Message text is displayed as plain text, never as executable HTML.
Reading and downloading do not rewrite the original evidence or its hashes. In WSL, the button converts the Linux
path and opens Windows File Explorer. Native Windows, macOS and Linux file
managers are also supported. The file manager opens on the Python host. If no
file manager is available, the page gives a manual folder path. Opening a folder
does not edit or rehash evidence. The completion notice is inside the app; it does
not request desktop-notification permission.

Use **Cancel and finalize** to stop safely. Reloading the page does not cancel
an active job; the same server job and any waiting login prompt reappear.
Ctrl+C shuts down the server and cancels/finalizes the active job.

## Small architecture

- `evidex_next.html`: native HTML/CSS/JavaScript form and status polling. No
  terminal emulator, WebSocket bridge, frontend build or browser storage.
- `evidex_next.py`: a local HTTP server and one acquisition task, on the same
  asyncio loop as every Telethon operation. Only one job runs at a time.
- `telegram_connection.py`: shared transport creation, bounded connection,
  diagnostics and cleanup. Next uses standard TCP and obfuscated TCP, which
  passed the operator's standalone test. It excludes the HTTP/TLS fallback that
  failed there. The original application retains all three transports.
- `evidence_store.py`: atomic JSON writing and SHA-256 helpers shared by both
  entry points. Next writes a new evidence directory for every acquisition.

## Sessions, proxies and files

Acquisition uses the selected `.session` file, or the phone-derived managed
session under `.evidex_sessions`. Session files are never deleted or replaced as
an automatic recovery step. To reuse an old account session, choose its absolute
path explicitly. Close other EVIDEX instances using that session first. A new
checkout uses its own relative session/export directories by default.

Proxy settings are explicit in the form. Generic ALL_PROXY is ignored. Next does
not prefill credentials, proxies or sessions from environment variables. You may
set EVIDEX_SESSION_DIR and EVIDEX_EXPORT_DIR for storage paths and
EVIDEX_CONNECT_TIMEOUT for an attempt budget from 1 to 300 seconds.

Credentials are not put in status responses or written to browser storage/logs.
The authorized Telegram session itself is an account credential: protect it.
The server binds to 127.0.0.1, uses a per-launch request token and rejects other
Host values. Do not expose it through public tunnels or bind it to a public host.
Files remain on the machine running Python; the app does not provide downloads.

## Verification and limits

Run the native tests with:

```bash
python3 -m unittest discover -s tests -p 'test_evidex_next.py' -v
```

Native tests use mocked Telegram clients and real local HTTP routes. They exercise connection-test isolation,
authorized acquisition, code/two-factor prompts, secret-safe errors, single-job
handling, page reload continuity, cancellation and partial evidence finalization.
For the entire repository suite, install `requirements-web.txt` as well and run
`python3 -m unittest discover -s tests -v`.
The browser-script checks can also be run with `node tests/test_next_ui.cjs`
when Node.js is available; Node.js is not required to run the app.

This removes the terminal/browser bridge and implicit connection settings.
It cannot guarantee that Telegram endpoints are reachable on every network.
Live account authorization and acquisition must still be confirmed locally;
no real Telegram credentials were used during development.
