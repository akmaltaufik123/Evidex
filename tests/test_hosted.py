"""No live Telegram or hosting credentials. Cross-workspace regression tests."""
import asyncio
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile
from aiohttp import DummyCookieJar
from aiohttp.test_utils import TestClient, TestServer
from evidex_hosted import create_app, COOKIE, USERS_KEY
from test_evidex_next import fake_client, PAYLOAD


class HostedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(public_url='http://evidex.test', data_root=self.root, secret='x'*64, secure_cookies=False)
        self.client = TestClient(TestServer(self.app), cookie_jar=DummyCookieJar())
        await self.client.start_server()
        self.a = await self.workspace()
        self.b = await self.workspace()

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def workspace(self):
        response = await self.client.get('/', headers={'Host':'evidex.test'})
        self.assertEqual(response.status, 200)
        html = await response.text()
        value = response.cookies[COOKIE].value
        return {'Host':'evidex.test', 'Cookie':COOKIE+'='+value,
                'X-Evidex-Token':re.search(r"const token='([^']+)'", html)[1]}

    def ws(self, headers):
        key = headers['Cookie'].split('=',1)[1].split('.')[0]
        return self.app[USERS_KEY][key]

    def case(self, headers):
        case = self.ws(headers).root / 'exports' / 'EVIDEX_fixture'
        case.mkdir(parents=True)
        (case/'messages.jsonl').write_text(json.dumps({'message_id':0,'text':'private sentinel'})+'\n')
        (case/'acquisition_report.json').write_text('{"status":"complete"}')
        (case/'messages.xlsx').write_bytes(b'xlsx sentinel')
        (case/'manifest.sha256').write_text('fixture')
        return case

    async def test_cookie_security_and_host_token_origin_checks(self):
        response=await self.client.get('/',headers=self.a)
        self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
        self.assertNotIn('id="session"',await response.text())
        self.assertEqual((await self.client.get('/api/state',headers={'Host':'evidex.test'})).status,401)
        bad=dict(self.a);bad['X-Evidex-Token']=self.b['X-Evidex-Token']
        self.assertEqual((await self.client.get('/api/state',headers=bad)).status,403)
        bad=dict(self.a,Origin='https://evil.invalid')
        self.assertEqual((await self.client.post('/api/cancel',headers=bad,json={})).status,403)
        self.assertEqual((await self.client.get('/',headers={'Host':'evil.invalid'})).status,403)
        self.assertEqual((await self.client.get('/health')).status,200)
        response=await self.client.get('/',headers={'Host':'evidex.test'})
        cookie=response.cookies[COOKIE]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'],'Strict')

    async def test_results_and_downloads_are_private(self):
        case=self.case(self.a)
        for route in ('messages','download','attachment'):
            response=await self.client.get('/api/'+route,params={'case':case.name,'path':'messages.jsonl'},headers=self.b)
            self.assertEqual(response.status,400)
        result=await (await self.client.get('/api/results',headers=self.b)).json()
        self.assertEqual(result['cases'],[])
        result=await (await self.client.get('/api/results',headers=self.a)).json()
        self.assertEqual(result['cases'][0]['path'],case.name)
        response=await self.client.get('/api/download',params={'case':case.name},headers=self.a)
        self.assertEqual(response.status,200)
        archive=zipfile.ZipFile(io.BytesIO(await response.read()))
        self.assertIn('messages.xlsx',archive.namelist())
        self.assertFalse(any('session' in name for name in archive.namelist()))
        response=await self.client.get('/api/download',params={'case':case.name,'kind':'excel'},headers=self.a)
        self.assertEqual(await response.read(),b'xlsx sentinel')

    async def test_delete_and_history_cannot_touch_other_workspace(self):
        case=self.case(self.a)
        response=await self.client.post('/api/delete-result',headers=self.b,json={'case':case.name,'confirmed':True})
        self.assertEqual(response.status,400)
        self.assertTrue(case.exists())
        await self.client.post('/api/clear-history',headers=self.b,json={'confirmed':True})
        self.assertTrue((case/'messages.jsonl').exists())
        response=await self.client.post('/api/delete-result',headers=self.a,json={'case':case.name,'confirmed':True})
        self.assertEqual(response.status,200)
        self.assertFalse(case.exists())

    async def test_acquisition_is_scoped_and_persists_excel(self):
        with patch('evidex_next.connect_client',new=AsyncMock(return_value=fake_client())):
            response=await self.client.post('/api/run',headers=self.a,json=dict(PAYLOAD,server_consent=True))
            self.assertEqual(response.status,200)
            await self.ws(self.a).engine.task
        engine=self.ws(self.a).engine
        self.assertEqual(engine.state['stage'],'complete')
        case=Path(engine.state['output'])
        self.assertTrue(case.is_relative_to(self.ws(self.a).root))
        self.assertTrue((case/'messages.xlsx').exists())
        self.assertEqual(self.ws(self.b).engine.state['messages'],0)
        state=await (await self.client.get('/api/state',headers=self.a)).json()
        self.assertNotIn(str(self.root),json.dumps(state))

    async def test_no_server_paths_proxies_or_unbounded_jobs(self):
        for fields in ({'server_consent':False},{'session':'/tmp/anything.session'},{'proxy':'socks5://127.0.0.1:1'},{'limit':'5001'}):
            response=await self.client.post('/api/run',headers=self.a,json=dict(PAYLOAD,server_consent=True,**fields)) if 'server_consent' not in fields else await self.client.post('/api/run',headers=self.a,json=dict(PAYLOAD,**fields))
            self.assertEqual(response.status,400)
        self.assertEqual((await self.client.post('/api/open-folder',headers=self.a,json={})).status,404)

    async def test_signed_cookie_is_not_forgeable(self):
        bad=dict(self.a);bad['Cookie']=bad['Cookie'][:-1]+('0' if bad['Cookie'][-1]!='0' else '1')
        self.assertEqual((await self.client.get('/api/state',headers=bad)).status,401)

    async def test_saved_results_survive_restart_with_same_signed_cookie(self):
        case=self.case(self.a)
        app=create_app(public_url='http://evidex.test',data_root=self.root,secret='x'*64,secure_cookies=False)
        client=TestClient(TestServer(app),cookie_jar=DummyCookieJar())
        await client.start_server()
        try:
            response=await client.get('/api/results',headers=self.a)
            self.assertEqual(response.status,200)
            self.assertEqual((await response.json())['cases'][0]['name'],case.name)
        finally:
            await client.close()

    async def test_capacity_and_disk_limit_block_new_jobs(self):
        from types import SimpleNamespace
        with patch('evidex_hosted.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            response=await self.client.post('/api/run',headers=self.a,json=dict(PAYLOAD,server_consent=True))
        self.assertEqual(response.status,503)
        self.assertFalse(self.ws(self.a).engine.state['busy'])

    async def test_production_cookie_has_secure_prefix_and_attributes(self):
        app=create_app(public_url='https://evidex.test',data_root=self.root,secret='x'*64)
        client=TestClient(TestServer(app),cookie_jar=DummyCookieJar())
        await client.start_server()
        try:
            response=await client.get('/',headers={'Host':'evidex.test'})
            cookie=response.cookies[COOKIE]
            self.assertTrue(cookie['secure'])
            self.assertTrue(cookie['httponly'])
            self.assertEqual(cookie['path'],'/')
            self.assertFalse(cookie['domain'])
        finally:
            await client.close()

    def test_missing_config_fails_closed(self):
        with self.assertRaises(ValueError):
            create_app(public_url='http://evidex.test',data_root=self.root,secret='x'*64)
        with self.assertRaises(ValueError):
            create_app(public_url='https://evidex.test',data_root=self.root,secret='short')
