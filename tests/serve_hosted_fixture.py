"""UI QA only: isolated temp storage and mock Telegram, never real credentials."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock
from aiohttp import web
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidex_hosted
import evidex_next
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_evidex_next import fake_client

# Browser QA uses HTTP only. Production always uses __Host- and Secure on HTTPS.
evidex_hosted.COOKIE='evidex-ui-test'
evidex_next.connect_client=AsyncMock(side_effect=lambda *args,**kwargs:fake_client())
storage=tempfile.TemporaryDirectory()
app=evidex_hosted.create_app(public_url='http://127.0.0.1:8795',data_root=Path(storage.name),secret='fixture-only-'*8,secure_cookies=False)
if __name__=='__main__':
    web.run_app(app,host='127.0.0.1',port=8795,access_log=None,print=None)
