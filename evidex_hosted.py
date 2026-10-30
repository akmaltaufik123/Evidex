"""Railway entry point: isolated browser workspaces, never the shared localhost API."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import time
from urllib.parse import urlsplit
import zipfile
from aiohttp import web
from evidex_next import Engine, validate, evidence_case, recent_evidence
from evidence_store import write_json

COOKIE = '__Host-evidex'
COOKIE_AGE = 30 * 86400
WORKSPACE_KEY = web.AppKey('workspace', object)
USERS_KEY = web.AppKey('hosted_users', dict)
BASE = Path(__file__).resolve().parent
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
           'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer',
           'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}

class Workspace:
    def __init__(self, root: Path, token: str):
        self.root, self.token = root, token
        self.engine = Engine()
        self.lock = asyncio.Lock()
        self.started: list[float] = []
        self.last_seen = time.monotonic()
        self.watchdog: asyncio.Task | None = None


def create_app(*, public_url: str | None = None, data_root: Path | None = None,
               secret: str | None = None, secure_cookies: bool = True) -> web.Application:
    public_url = (public_url or os.environ.get('EVIDEX_PUBLIC_URL', '')).rstrip('/')
    parsed = urlsplit(public_url)
    if not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('Set EVIDEX_PUBLIC_URL to the external HTTPS origin, without a path.')
    if parsed.scheme != 'https' and secure_cookies:
        raise ValueError('Hosted mode requires an HTTPS public URL.')
    secret = secret or os.environ.get('EVIDEX_SECRET', '')
    if len(secret) < 32:
        raise ValueError('Set EVIDEX_SECRET to a random secret of at least 32 characters.')
    root = (data_root or Path(os.environ.get('EVIDEX_DATA_DIR', '/data/evidex'))).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    users: dict[str, Workspace] = {}
    max_jobs = int(os.environ.get('EVIDEX_MAX_JOBS', '2'))
    max_users = int(os.environ.get('EVIDEX_MAX_WORKSPACES', '128'))
    quota = int(os.environ.get('EVIDEX_USER_QUOTA_MB', '256')) * 1024 * 1024
    lifetime = int(os.environ.get('EVIDEX_JOB_TIMEOUT', '900'))
    if min(max_jobs, max_users, quota, lifetime) <= 0:
        raise ValueError('Hosted capacity limits must be positive.')

    def sign(value):
        return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()

    def identity(value):
        parts = value.split('.')
        if len(parts) != 3 or not re.fullmatch(r'[a-f0-9]{64}', parts[0]) or not parts[1].isdigit():
            return None
        if not hmac.compare_digest(sign('.'.join(parts[:2])), parts[2]):
            return None
        age = int(time.time()) - int(parts[1])
        return parts[0] if 0 <= age <= COOKIE_AGE else None

    def usage(directory):
        return sum(p.stat().st_size for p in directory.rglob('*') if p.is_file() and not p.is_symlink()) if directory.exists() else 0

    @web.middleware
    async def guard(request, handler):
        if request.path == '/health':
            return web.json_response({'ok': True}, headers={'Cache-Control': 'no-store'})
        if request.host != parsed.netloc:
            raise web.HTTPForbidden(text='Use the configured EVIDEX address.')
        cookie = None
        if request.path == '/' or request.path.startswith('/api/'):
            key = identity(request.cookies.get(COOKIE, ''))
            if key is None:
                if request.path != '/':
                    raise web.HTTPUnauthorized(text='Reload EVIDEX to open your workspace.')
                if len(users) >= max_users or len(list(root.glob('user_*'))) >= max_users:
                    raise web.HTTPServiceUnavailable(text='Workspace capacity reached. Please try later.')
                key = secrets.token_hex(32)
                payload = key + '.' + str(int(time.time()))
                cookie = payload + '.' + sign(payload)
            if key not in users:
                users[key] = Workspace(root / ('user_' + key), sign('csrf.' + key))
            ws = users[key]
            ws.last_seen = time.monotonic()
            request[WORKSPACE_KEY] = ws
            if request.path.startswith('/api/'):
                if not hmac.compare_digest(request.headers.get('X-Evidex-Token', ''), ws.token):
                    raise web.HTTPForbidden(text='Reload your EVIDEX page.')
                if request.method == 'POST' and request.headers.get('Origin') not in (None, public_url):
                    raise web.HTTPForbidden(text='Invalid request origin.')
        try:
            response = await handler(request)
        except (ValueError, json.JSONDecodeError):
            response = web.json_response({'error': 'Invalid request. Check the selected result and fields.'}, status=400)
        except OSError:
            response = web.json_response({'error': 'Storage operation failed. Please try again.'}, status=503)
        if not response.prepared:
            response.headers.update(HEADERS)
            if cookie:
                response.set_cookie(COOKIE, cookie, max_age=COOKIE_AGE, secure=secure_cookies,
                                    httponly=True, samesite='Strict', path='/')
        return response

    app = web.Application(middlewares=[guard], client_max_size=32 * 1024)
    app[USERS_KEY] = users

    async def payload(request):
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data

    def exports(ws):
        return ws.root / 'exports'

    def selected(ws, name):
        return evidence_case(name, exports(ws))

    async def index(request):
        ws = request[WORKSPACE_KEY]
        catalog = json.loads((BASE / 'evidex_next_content.json').read_text())
        for lang, words in {
            'ms': {'intro': 'Sambungkan akaun Telegram sendiri, kumpul bukti dan muat turun hasil. Sesi Telegram serta bukti diproses pada server ATE.', 'openFolder': 'Muat turun ZIP', 'workspace': 'Ruang kerja web', 'footer': 'Bukti disimpan pada server ATE sehingga anda memadamnya. Ruang kerja ini diakses melalui cookie browser ini, bukan akaun berdaftar. Simpan salinan ZIP anda; kehilangan cookie bermaksud kehilangan akses melalui browser. Jangan kongsi cookie, kod login atau fail sesi.', 'completeHint': 'Semak mesej, kemudian muat turun ZIP atau Excel. Anda sendiri memilih apa yang hendak dikongsi.', 'keepOpen': 'Kerja diteruskan jika halaman dimuat semula. Gunakan browser yang sama. Restart server akan menghentikan kerja aktif; hasil separa akan disimpan jika shutdown sempat selesai.', 'advancedHint': '', 'limitPlaceholder': '1 hingga 5000 (lalai 500)', 'credentialsHint': 'API ID dan hash diperlukan oleh Telegram. Buka panduan untuk mendapatkannya. Ia dihantar melalui HTTPS ke server ATE untuk sambungan anda.'},
            'en': {'intro': 'Connect your own Telegram account, collect evidence and download results. Telegram sessions and evidence are processed on the ATE server.', 'openFolder': 'Download ZIP', 'workspace': 'Web workspace', 'footer': 'Evidence stays on the ATE server until you delete it. This workspace is accessed through this browser cookie, not a registered account. Keep your ZIP copy; losing the cookie means losing browser access. Never share cookies, login codes or session files.', 'completeHint': 'Review messages, then download ZIP or Excel. You choose what to share.', 'keepOpen': 'Reloading does not stop the job. Use the same browser. Server restarts stop active jobs; partial results are saved when graceful shutdown completes.', 'advancedHint': '', 'limitPlaceholder': '1 to 5000 (default 500)', 'credentialsHint': 'Telegram requires an API ID and hash. Open the guide to obtain them. They are sent over HTTPS to the ATE server for your connection.'}
        }.items():
            catalog[lang].update(words)
        html = (BASE / 'evidex_next.html').read_text()
        html = re.sub(r'<details><summary><span data-i18n="advanced"[\s\S]*?</details>', '', html, count=1)
        html = html.replace('</body>', '<script src="/hosted.js"></script></body>')
        # External hosted script is explicitly same-origin; no third-party code.
        return web.Response(text=html.replace('__TOKEN__', ws.token).replace('__COPY__', json.dumps(catalog, ensure_ascii=False).replace('<', r'\u003c')), content_type='text/html', headers={**HEADERS, 'Content-Security-Policy': HEADERS['Content-Security-Policy'].replace("script-src 'unsafe-inline'", "script-src 'self' 'unsafe-inline'")})

    async def state(request):
        ws = request[WORKSPACE_KEY]
        state = dict(ws.engine.state)
        if state['output']:
            state['output'] = Path(state['output']).name
        return web.json_response(state)

    async def run(request):
        ws = request[WORKSPACE_KEY]
        data = await payload(request)
        if data.get('server_consent') is not True:
            return web.json_response({'error': 'Confirm server processing consent before connecting.'}, status=400)
        if data.get('session') or data.get('proxy'):
            raise ValueError()
        if sum(w.engine.state['busy'] for w in users.values()) >= max_jobs:
            return web.json_response({'error': 'Server is busy. Try again after another job finishes.'}, status=429)
        now = time.monotonic()
        ws.started = [value for value in ws.started if value > now - 3600]
        if len(ws.started) >= 6:
            return web.json_response({'error': 'Workspace hourly limit reached. Try later.'}, status=429)
        if shutil.disk_usage(root).free < 256 * 1024 * 1024:
            return web.json_response({'error': 'Server storage is low. Try later.'}, status=503)
        if usage(ws.root) >= quota:
            return web.json_response({'error': 'Workspace storage limit reached. Download and delete old results first.'}, status=409)
        if data.get('mode') == 'acquire':
            data['limit'] = str(data.get('limit', '')).strip() or '500'
            if not data['limit'].isascii() or not data['limit'].isdigit() or not 1 <= int(data['limit']) <= 5000:
                raise ValueError()
        try:
            config = validate(data, output_root=exports(ws), session_root=ws.root / 'sessions')
            config.update(max_media_file_bytes=16 * 1024 * 1024, max_media_bytes=64 * 1024 * 1024)
            ws.engine.start(config)
        except ValueError as error:
            return web.json_response({'error': str(error)}, status=400)
        ws.started.append(now)
        async def supervise():
            await asyncio.wait_for(asyncio.shield(ws.engine.task), timeout=lifetime)
        async def watchdog():
            try:
                await supervise()
            except asyncio.TimeoutError:
                await ws.engine.close()
        ws.watchdog = asyncio.create_task(watchdog())
        return web.json_response({'ok': True})

    async def answer(request):
        data = await payload(request)
        if not isinstance(data.get('answer'), str):
            raise ValueError()
        request[WORKSPACE_KEY].engine.respond(data['answer'])
        return web.json_response({'ok': True})

    async def cancel(request):
        request[WORKSPACE_KEY].engine.cancel()
        return web.json_response({'ok': True})

    async def results(request):
        cases = recent_evidence(exports(request[WORKSPACE_KEY]))
        for case in cases:
            case['path'] = case['name']
        return web.json_response({'cases': cases})

    async def messages(request):
        ws = request[WORKSPACE_KEY]
        case = selected(ws, request.query.get('case'))
        offset = int(request.query.get('offset', '0'))
        if offset < 0:
            raise ValueError()
        query = request.query.get('q', '').casefold()[:200]
        records, matched, more = [], 0, False
        path = case / 'messages.jsonl'
        if path.is_symlink():
            raise ValueError()
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                record = json.loads(line)
                if query not in str(record.get('text', '')).casefold():
                    continue
                if matched >= offset:
                    if len(records) == 50:
                        more = True
                        break
                    records.append({key: record.get(key) for key in ('message_id', 'sender_id', 'date_utc', 'text', 'media')})
                matched += 1
        return web.json_response({'messages': records, 'offset': offset, 'more': more})

    async def download(request):
        ws = request[WORKSPACE_KEY]
        if ws.engine.state['busy']:
            return web.json_response({'error': 'Wait for the job to finish first.'}, status=409)
        async with ws.lock:
            case = selected(ws, request.query.get('case'))
            kind = request.query.get('kind', 'zip')
            with tempfile.TemporaryDirectory(prefix='evidex-download-') as temporary:
                if kind == 'excel':
                    path, name = case / 'messages.xlsx', case.name + '.xlsx'
                    if not path.is_file() or path.is_symlink():
                        raise ValueError()
                elif kind == 'zip':
                    path, name = Path(temporary) / 'evidence.zip', case.name + '.zip'
                    def pack():
                        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
                            for file in case.rglob('*'):
                                if file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(case):
                                    archive.write(file, file.relative_to(case).as_posix())
                    await asyncio.to_thread(pack)
                else:
                    raise ValueError()
                response = web.StreamResponse(headers={**HEADERS, 'Content-Type': 'application/octet-stream', 'Content-Disposition': f'attachment; filename="{name}"'})
                response.content_length = path.stat().st_size
                await response.prepare(request)
                with path.open('rb') as handle:
                    while chunk := handle.read(256 * 1024):
                        await response.write(chunk)
                await response.write_eof()
                return response

    async def attachment(request):
        ws = request[WORKSPACE_KEY]
        case = selected(ws, request.query.get('case'))
        path = (case / request.query.get('path', '')).resolve()
        if not path.is_relative_to(case / 'media') or not path.is_file():
            raise ValueError()
        return web.FileResponse(path, headers={**HEADERS, 'Content-Disposition': 'attachment'})

    async def delete_result(request):
        ws = request[WORKSPACE_KEY]
        data = await payload(request)
        if data.get('confirmed') is not True:
            raise ValueError()
        if ws.engine.state['busy']:
            return web.json_response({'error': 'Wait for the job to finish first.'}, status=409)
        async with ws.lock:
            shutil.rmtree(selected(ws, data.get('case')))
        return web.json_response({'ok': True})

    async def clear_history(request):
        ws = request[WORKSPACE_KEY]
        if (await payload(request)).get('confirmed') is not True:
            raise ValueError()
        if ws.engine.state['busy']:
            return web.json_response({'error': 'Wait for the job to finish first.'}, status=409)
        async with ws.lock:
            directory = exports(ws)
            directory.mkdir(parents=True, exist_ok=True)
            names = [p.name for p in directory.glob('EVIDEX_*') if p.is_dir() and not p.is_symlink()]
            write_json(directory / '.hidden_history.json', {'cases': names})
        return web.json_response({'ok': True})

    async def static(request):
        files = {'app.css': 'evidex_next.css', 'hosted.js': 'evidex_hosted.js'}
        name = request.match_info['name']
        if name not in files:
            raise web.HTTPNotFound()
        return web.FileResponse(BASE / files[name])

    async def asset(request):
        group, name = request.match_info['group'], request.match_info['name']
        directory = 'guide_assets' if group == 'guide-assets' else 'agency_assets'
        if not re.fullmatch(r'[a-z0-9-]+\.(webp|png)', name):
            raise web.HTTPNotFound()
        path = BASE / directory / name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def cleanup(app):
        for ws in users.values():
            if ws.watchdog:
                ws.watchdog.cancel()
        await asyncio.gather(*(ws.engine.close() for ws in users.values()), return_exceptions=True)
        await asyncio.gather(*(ws.watchdog for ws in users.values() if ws.watchdog), return_exceptions=True)

    async def health(request):
        return web.json_response({'ok': True})
    app.router.add_get('/health', health)
    app.router.add_get('/', index)
    for path, handler in [('state', state), ('results', results), ('messages', messages), ('download', download), ('attachment', attachment)]:
        app.router.add_get('/api/' + path, handler)
    for path, handler in [('run', run), ('answer', answer), ('cancel', cancel), ('delete-result', delete_result), ('clear-history', clear_history)]:
        app.router.add_post('/api/' + path, handler)
    app.router.add_get('/{group:guide-assets|agency-assets}/{name}', asset)
    app.router.add_get('/{name:app.css|hosted.js}', static)
    app.on_cleanup.append(cleanup)
    return app


def main():
    os.umask(0o077)
    web.run_app(create_app(), host='0.0.0.0', port=int(os.environ.get('PORT', '8000')), access_log=None)

if __name__ == '__main__':
    main()
