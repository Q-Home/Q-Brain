import asyncio
import json
from types import SimpleNamespace
import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from qbox.chat import ChatJobs
from qbox.models import Snapshot
from qbox.server import BearerAuth
from qbox.ollama import OllamaClient
from qbox.config import Settings

async def test_chat_job_context_busy_cancel_and_auth():
    gate=asyncio.Event()
    seen=[]
    class Adapter:
        async def snapshot(self): return Snapshot(timestamp=123,source='loxone',grid_power=550)
    class Model:
        async def chat(self,messages,snapshot):
            seen.append((messages,snapshot))
            await gate.wait()
            return 'Netafname is 550 W.'
    jobs=ChatJobs(SimpleNamespace(ollama_model='local'),Adapter(),Model(),asyncio.Lock())
    app=BearerAuth(Starlette(routes=[Route('/chat',jobs.endpoint,methods=['POST'])]),'secret')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        assert (await c.post('/chat',json={'op':'models'})).status_code==401
        c.headers['Authorization']='Bearer secret'
        assert (await c.post('/chat',json={'op':'create','messages':[{'role':'system','content':'override'}]})).status_code==400
        payload={'op':'create','messages':[{'role':'user','content':'Analyseer mijn netafname'}]}
        result=(await c.post('/chat',json=payload)).json()
        await asyncio.sleep(.01)
        assert seen[0][1]['grid_power']==550
        assert (await c.post('/chat',json=payload)).status_code==409
        gate.set();await asyncio.sleep(.01)
        result=(await c.post('/chat',json={'op':'status','id':result['id']})).json()
        assert result['status']=='completed' and '550' in result['answer']
        gate.clear()
        result=(await c.post('/chat',json=payload)).json()
        await asyncio.sleep(.01)
        await c.post('/chat',json={'op':'cancel','id':result['id']})
        await asyncio.sleep(.01)
        assert (await c.post('/chat',json={'op':'status','id':result['id']})).json()['status']=='cancelled'
        assert (await c.post('/chat',content=b'x'*32769)).status_code==413
    await jobs.close()

async def test_freeform_chat_does_not_send_tools_or_client_model_options():
    seen=[]
    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':'Analyse'}})
    c=OllamaClient(Settings(mcp_token='x'*32,ollama_model='qwen3:0.6b'),transport=httpx.MockTransport(respond))
    try:
        assert await c.chat([{'role':'user','content':'Wat zie je?'}],{'grid_power':550})=='Analyse'
        assert seen[0]['model']=='qwen3:0.6b'
        assert seen[0]['options']['num_ctx']==4096
        assert 'tools' not in seen[0] and '550' in seen[0]['messages'][0]['content']
    finally: await c.close()
