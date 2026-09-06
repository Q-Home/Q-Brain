"""Bounded, in-memory chat jobs. The browser owns conversation history."""
import asyncio
import json
import secrets
import time
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from starlette.responses import JSONResponse
from .ollama import analysis_failure

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=3000)

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(min_length=1, max_length=8)

class ChatJobs:
    def __init__(self, config, adapter, ollama, lock):
        self.config, self.adapter, self.ollama, self.lock = config, adapter, ollama, lock
        self.jobs = {}
        self.tasks = {}

    async def close(self):
        for task in self.tasks.values(): task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    async def run(self, key, messages):
        try:
            async with asyncio.timeout(660):
                async with self.lock:
                    self.jobs[key]['status'] = 'running'
                    try:
                        snapshot = (await self.adapter.snapshot()).model_dump()
                        snapshot['observations'] = snapshot.get('observations', [])[:12]
                    except Exception:
                        snapshot = {'error':'Actuele meetgegevens ontbreken of zijn verouderd; verzin geen waarden.'}
                    answer = await self.ollama.chat(messages, snapshot)
                    self.jobs[key].update(status='completed', answer=answer)
        except asyncio.CancelledError:
            self.jobs[key].update(status='cancelled')
            raise
        except Exception as error:
            self.jobs[key].update(status='failed', error=analysis_failure(error)['message'])
        finally:
            self.jobs[key]['updated'] = time.time()

    async def endpoint(self, request):
        raw = b''
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 32768: return JSONResponse({'error':'Vraag te groot.'}, 413)
        try:
            data = json.loads(raw)
            op = data['op']
            if op == 'models':
                return JSONResponse({'model':self.config.ollama_model})
            if op == 'create':
                if set(data) != {'op','messages'}: raise ValueError()
                parsed = ChatRequest(messages=data['messages'])
                if sum(len(m.content) for m in parsed.messages)>6000: raise ValueError()
                if parsed.messages[-1].role != 'user': raise ValueError()
                if any(not task.done() for task in self.tasks.values()):
                    return JSONResponse({'error':'Er loopt al een chatvraag. Wacht op het antwoord.'}, 409)
                for key in list(self.jobs):
                    if time.time()-self.jobs[key]['updated'] > 600:
                        self.jobs.pop(key); self.tasks.pop(key, None)
                if len(self.jobs) >= 32:
                    key=min(self.jobs, key=lambda k:self.jobs[k]['updated'])
                    self.jobs.pop(key);self.tasks.pop(key,None)
                key = secrets.token_hex(24)
                self.jobs[key] = {'status':'queued', 'updated':time.time()}
                self.tasks[key] = asyncio.create_task(self.run(key, [m.model_dump() for m in parsed.messages]))
                return JSONResponse({'id':key, 'status':'queued'})
            if op in ('status','cancel'):
                key = data['id']
                if key not in self.jobs: return JSONResponse({'error':'Gesprekstaak verlopen. Stel je vraag opnieuw.'}, 404)
                if op == 'cancel' and not self.tasks[key].done():
                    self.jobs[key].update(status='cancelled')
                    self.tasks[key].cancel()
                return JSONResponse(self.jobs[key])
            raise ValueError()
        except (ValueError, TypeError, KeyError):
            return JSONResponse({'error':'Ongeldige chatvraag.'}, 400)
