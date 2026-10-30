"""Local UI preview only: no Telegram, sessions or evidence writes."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent

class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/':
            body = (ROOT / 'evidex_next.html').read_text().replace('__COPY__', (ROOT / 'evidex_next_content.json').read_text().replace('<', r'\u003c')).replace('__TOKEN__', 'preview-only')
            body = body.replace('<main class="wrap">', '<main class="wrap"><p role="status">Preview sahaja / Layout preview only. Tiada sambungan Telegram. Gunakan data contoh.</p>')
            return self.send(body.encode(), 'text/html; charset=utf-8')
        if path == '/app.css':
            return self.send((ROOT / 'evidex_next.css').read_bytes(), 'text/css')
        if path.startswith('/agency-assets/'):
            name = path.removeprefix('/agency-assets/')
            if name in {'mcmc.png', 'pdrm.png', 'nsrc.png', 'cybersecurity-malaysia.png'}:
                return self.send((ROOT / 'agency_assets' / name).read_bytes(), 'image/png')
        if path.startswith('/guide-assets/'):
            name = path.removeprefix('/guide-assets/')
            if '/' not in name and name.endswith('.webp') and (ROOT / 'guide_assets' / name).is_file():
                return self.send((ROOT / 'guide_assets' / name).read_bytes(), 'image/webp')
        if path == '/api/state':
            return self.send(json.dumps(dict(busy=False, stage='ready', mode=None, messages=0, media=0, prompt=None, error=None, output=None, logs=['PREVIEW · Tiada sambungan Telegram / No Telegram connection.', 'PREVIEW · Borang kiri / Fields left.', 'PREVIEW · Kawalan kanan / Controls right.', 'PREVIEW · Log berasingan di bawah / Separate activity log below.'])).encode(), 'application/json')
        if path == '/api/results':
            return self.send(b'{"cases":[]}', 'application/json')
        self.send_error(404)

    def do_POST(self):
        self.send(b'{"error":"Layout preview only. Telegram actions are disabled."}', 'application/json', 409)

    def send(self, body, mime, status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

if __name__ == '__main__':
    print('EVIDEX layout preview: http://127.0.0.1:8081 · Ctrl+C to stop', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8081), Preview).serve_forever()
