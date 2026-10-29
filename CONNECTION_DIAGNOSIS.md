# Telegram connection architecture (2.2.0)

## What changed

`evidex.py` owns the terminal/browser interface, authorization prompts and evidence
acquisition. `telegram_connection.py` owns client construction, transport fallback,
connection deadlines and failed-client cleanup. The UI delegates to one connector;
no thread switching or alternate browser-specific Telegram client is involved.

The previous implementation inherited ALL_PROXY and automatically selected a
nearby session file. Either could make the UI differ from the operator's direct,
fresh StringSession diagnostic. Connections are now direct unless a proxy is
explicitly supplied through the form or EVIDEX_PROXY_URL; an existing session
is selected only through the form or EVIDEX_SESSION_PATH. Managed account sessions
continue to use their existing phone-derived filenames. No sessions are deleted,
replaced or silently changed after a failure.

New transport attempts use the supplied successful baseline: socket timeout 10s,
connection_retries=1, request_retries=1 and outer deadline 15s. Saved files, whether
managed or selected, get a 60s outer deadline and the same single-retry policy.
EVIDEX_CONNECT_TIMEOUT overrides either deadline (finite 1–300 seconds). This
normalizes the previous 6/8s and 10/60s policies; it is not proof that timeouts were
the original cause. All three fallback transports remain, including accurately
labelled HTTP MTProto. HTTP MTProto is not a website reachability check.

Cancellation and ApiIdInvalidError propagate after bounded cleanup. Configuration
and session-construction errors fail directly rather than being called network
timeouts. Exhausted transports raise ConnectionError rather than a blanket
TimeoutError. Diagnostics use fixed safe messages instead of arbitrary exception
text that may contain credentials.

## Verification and limits

`python3 evidex.py --check-connection` uses the same connector with an explicit
fresh in-memory session and no proxy, without Textual, account login or writes to
saved sessions. It intentionally does not prove authorization or acquisition.
Never share API hashes, login codes or session files.

Unit tests cover configuration forwarding, policies, fallback, constructor errors,
cleanup, cancellation, API rejection, secret-safe messages, explicit defaults,
connection checking and browser launching. A mocked full Textual extraction
connects, checks authorization, acquires a fixture message, writes output and
verifies every manifest digest. Other tests cover two-factor prompts and control
recovery after total connection failure. Browser HTTP/WebSocket smoke tests verify
rendering and F1 interaction without a Telegram account.

The original live Telegram failure cannot be reproduced without the operator's
environment. Hidden proxy/session settings and early cancellation are candidate
causes, not confirmed causes. No real Telegram login or acquisition was performed
in this workspace. Run the connection check and retain the latest sanitized log
if the new version still fails.
