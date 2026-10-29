"""Local-only UI QA fixture. Never contacts Telegram; not an application launcher."""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from telethon.errors import SessionPasswordNeededError
import evidex_next

fixture = tempfile.TemporaryDirectory()
os.environ['EVIDEX_SESSION_DIR'] = fixture.name + '/sessions'
os.environ['EVIDEX_EXPORT_DIR'] = fixture.name + '/exports'
case = Path(os.environ['EVIDEX_EXPORT_DIR']) / 'EVIDEX_sample_fixture'
case.mkdir(parents=True)
(case / 'acquisition_report.json').write_text(json.dumps({'status': 'complete'}))
(case / 'messages.jsonl').write_text(json.dumps({'message_id': 1, 'sender_id': 7, 'text': 'Sample evidence for UI testing only.', 'date_utc': '2026-10-30T00:00:00+00:00', 'media': None}) + '\n')

async def connect(*args, **kwargs):
    client = MagicMock()
    client.disconnect = AsyncMock()
    client.is_user_authorized = AsyncMock(side_effect=[False, True])
    client.send_code_request = AsyncMock()
    client.sign_in = AsyncMock(side_effect=[SessionPasswordNeededError(request=None), None])
    client.get_entity = AsyncMock(return_value=SimpleNamespace(id=42))
    async def messages(*args, **kwargs):
        yield SimpleNamespace(id=1, date=datetime.now(timezone.utc), edit_date=None,
            sender_id=7, post_author=None, raw_text='Sample evidence for UI testing only.',
            reply_to_msg_id=None, grouped_id=None, views=0, forwards=0, replies=None, media=None)
    client.iter_messages.side_effect = messages
    return client

evidex_next.connect_client = connect
if __name__ == '__main__':
    web.run_app(evidex_next.create_app(), host='127.0.0.1', port=8794, access_log=None, print=None)
