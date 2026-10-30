<!-- Hallmark · macrostructure: guided-workbench · theme: paper-ink · genre: modern-minimal
pre-emit critique: P4 H4 E4 S5 R5 V4 · slop test: pass (hosted UI sweep) -->
# EVIDEX hosted beta

`evidex_hosted.py` is a separate Railway entry point. Visitors only use a browser;
Python, Telethon and Excel dependencies are installed in the server Docker image.
The original localhost app and Textual entry point remain available.

## Railway configuration (operator only)

Create a separate `evidex-web` service in the existing project, production
environment. Do not replace ATEGateway or another existing service. Connect this
repository after the required variables and volume have been configured.

- Build: repository Dockerfile; railway.toml provides `/health` and one replica.
- Persistent volume: mount at `/data` (at least 1 GB recommended for the beta).
- `EVIDEX_DATA_DIR=/data/evidex`
- `EVIDEX_PUBLIC_URL`: the exact external HTTPS origin, no trailing path. Configure
  this after Railway issues a service domain. To switch to a custom subdomain,
  verify DNS/TLS first and then change this origin. Browser cookies do not transfer
  across domains: make this change before accepting real evidence.
- `EVIDEX_SECRET`: a stable, cryptographically random secret, at least 32
  characters. Generate it in the deployment tooling and set it directly as a
  Railway variable. Never commit or print it. Rotating it invalidates existing
  workspace cookies, so retain the value through ordinary redeployments.
- `PORT`: supplied by Railway; the process listens on 0.0.0.0.
- Optional limits: EVIDEX_MAX_JOBS=2, EVIDEX_MAX_WORKSPACES=128,
  EVIDEX_USER_QUOTA_MB=256, EVIDEX_JOB_TIMEOUT=900.

Observe deployment SUCCESS and check the real health endpoint, cookies and UI
before replacing website download links with a live-app link. A queued build or
an existing static introduction page is not a launched acquisition service.

## Isolation and privacy model

This beta uses private browser workspaces, not registered user accounts. A random
256-bit workspace ID is authenticated with a signed, HttpOnly, Secure, SameSite
Strict `__Host-` cookie. Cookies expire after 30 days. Do not share them. Losing
the cookie means losing browser access; export a ZIP copy. Persistent files are
not silently deleted when cookies expire. Operators must manage abandoned data
under their published retention policy before a wider public rollout.

Each workspace gets its own Engine, Telegram session directory, exports and
history index. All API calls also require a workspace-derived CSRF header.
Requests are confined to the configured Host; cross-origin POSTs are rejected.
Session/proxy paths from visitors are rejected. Existing local session files are
never selected or modified by hosted mode. API details and login answers go to
the server to connect to Telegram; consent is required before even a transport
test. Credentials are not put in result URLs or logs. Server-held Telegram
sessions remain in the protected workspace volume; only case exports can be
included in a download. Delete-result removes the chosen case, not session files.

The UI discloses server processing and cookie-based access. It replaces the local
folder opener with ZIP download and adds Excel download. Evidence text remains
text-only; downloads use a token header rather than a token in the URL. ZIPs
exclude links and stay inside the selected case. One workspace cannot read,
answer login prompts for, cancel, download or delete another workspace's job.

## Beta operating limits

- One running job per workspace; default two jobs across the instance.
- Six starts per hour per active workspace; default 500 messages, maximum 5000.
- Media: maximum 16 MiB per file and 64 MiB downloaded per job. Oversized or
  unknown-size media is recorded as a download error and skipped. Original JSONL
  still records available media metadata. Other media failures behave likewise.
- Jobs are stopped and finalized after 15 minutes by default, including login
  wait time. Large acquisitions may therefore be partial.
- A workspace at its pre-job storage threshold cannot start another acquisition;
  the check is a gate, not an exact hard byte ceiling during the current job.
- New jobs are rejected if free disk is below 256 MiB. This and the limits above
  are capacity controls, not an abuse-proof public service guarantee.
- One replica only. Process restarts stop in-flight jobs; graceful shutdown
  finalizes partial evidence. Saved results survive when the volume is mounted.
- Workspace capacity is deliberately bounded. Empty/expired workspaces require
  operator maintenance; there is no account recovery UI, scheduled retention
  cleanup, email login, CAPTCHA or horizontal job queue in this beta.

A broader rollout needs an explicit retention policy, account recovery design and
operational monitoring appropriate to evidence sensitivity. Do not describe the
beta as audited, court-certified or integrated with government complaint APIs.

## Validation

80 unit tests passed without live Telegram credentials. Hosted tests cover
workspace isolation, consent, host/origin/CSRF checks, signed-cookie tampering,
private message/download access, ZIP/Excel responses, deletion boundaries,
acquisition and configuration failures. The real-browser hosted sweep exercised
mock acquisition and both download controls in BM/English at
320/375/414/768/1280px; no page overflow or JavaScript failures. Original UI script
tests also passed. Tests do not prove live Telegram authorization or real hosting
performance.

## Current provisioning blocker

On 30 October 2026 Railway rejected creating the separate service with:
`Free plan resource provision limit exceeded. Please upgrade to provision more resources!`
Read-back confirmed no EVIDEX service was created. Existing production services
were left unchanged. Hosting is not live until this platform limit is resolved,
the volume and variables are configured, and a deployment reaches SUCCESS.
