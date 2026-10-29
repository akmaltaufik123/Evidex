# Telegram connection investigation

Inspected upstream revision: ebfac4b8684753364831886a7cf37943cb794942.
Validated with Python 3.12, Telethon 1.45.0 and Textual 6.12.0.

## Findings

The cause of the two TCP timeouts is not established. The supplied standalone
results demonstrate transport connection on that machine, not account
authorization or acquisition. No live Telegram login was performed here.

- The form passes the validated API ID/hash, parsed optional proxy and selected
  session into `ExtractionConfig`, then directly into `TelegramClient`. No code
  was found that substitutes API credentials or a proxy during fallback.
- Managed sessions use a phone-derived filename under `EVIDEX_SESSION_DIR`
  (default relative to the working directory). They persist between runs. The
  word “managed” does not mean a fresh session. A selected session uses the
  supplied resolved path. Neither path is replaced with `StringSession()`.
- Telethon's `connect()` uses the saved session's DC/address/port and auth key.
  A fresh `StringSession()` need not use the same endpoint or handshake path.
- Policy is selected by the explicit session field, not file existence:
  managed sessions use socket timeout 6s, 1 connection retry and outer budget 8s;
  selected sessions use 10s, 5 retries and outer budget 60s. The outer deadline
  includes connection initialization, beyond opening a TCP socket. It can cancel
  work before all retries finish. This is a plausible contributor, not a proven
  explanation. Policies remain unchanged pending measured evidence.
- The async Textual worker awaits connection and authorization on the same loop;
  no thread handoff or blocking `input()` occurs in this flow. Cancel cancels
  that worker. Failed candidates are disconnected before the next constructor;
  cleanup has a 3s deadline. A cleanup exception was previously hidden.
- Telethon 1.45.0 `ConnectionHttp` sends HTTP MTProto packets and enables TLS when
  its session port is 443. It is not a website reachability check. The observed
  TLS wrong-version error is consistent with a protocol/endpoint mismatch, but
  does not explain failure of the independent TCP transports. Fallback remains.
- This checkout cannot establish which file the operator's terminal executed.
  Startup now logs the source file and app version to make that comparison possible.

## Changes

Correct the HTTP transport label and premature authentication wording. Add
credential-safe failure descriptions, elapsed time, timeout budget, session
policy/file presence, DC/port and cleanup diagnostics. Exception text is mapped
to fixed descriptions rather than copying potentially sensitive proxy URLs,
request data, phone numbers or codes. Clear the active-client reference after
failed cleanup, including cancellation and API rejection paths. Preserve the
TUI, session selection, timeouts, retries, proxy and acquisition/export behavior.

## Further evidence needed

Run the edited file in the same virtual environment as the standalone test.
Record the startup source/version and connection policy, DC/port, transport,
elapsed/budget and cleanup lines. Verify the proxy field matches the standalone
setup. Compare the saved-session endpoint to the standalone session endpoint
locally without sharing session contents or credentials. Do not delete or replace
sessions to perform this comparison, and do not open the same SQLite session
concurrently in two clients.

If timeouts consistently land on the 8s boundary, a controlled comparison using
the same session, proxy, transport and retry policy with a longer outer budget
can establish whether cancellation is causal. The current logs intentionally
cannot tell whether an underlying socket timeout or the outer deadline raised
`TimeoutError`; elapsed time and a controlled comparison are required.

## Verification

Run `python -m unittest discover -s tests -v`,
`python -m compileall -q evidex.py tests`, and `git diff --check`.
Tests use mocks and require no real Telegram account. They cover direct success,
fallback to the second and third transports, cleanup order and cleanup failures,
cancellation, API rejection, both timeout/retry policies, managed file presence,
safe failure output, total failure, deadline cancellation, separation from
account authorization, and the existing TUI and integrity helpers. File-preservation
checks use a mocked client; they do not claim to test Telethon's SQLite writes.
