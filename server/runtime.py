"""Truthful, privacy-preserving runtime telemetry for the local Sayuri UI.

Never infer emotions, token usage, model pricing, graph-building or active jobs.
Everything shown here derives from actual requests and measured probes.
"""
from __future__ import annotations
import asyncio
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from uuid import uuid4

import httpx

_LOCK=RLock()
_JOBS={}
_EVENTS=deque(maxlen=24)
_CLOUD={"state":"unknown","model_id":None,"latency_ms":None,
        "last_error":None,"last_http_status":None,"last_success_at":None,
        "requests_count":0,"token_usage":None,"cost_rub":None}
_NETWORK={"state":"unknown","latency_ms":None,"last_success_at":None,"failure_reason":None}
_NET_NEXT=0.0
_CLOUD_NEXT=0.0
_NET_PROBING=False
_CLOUD_PROBING=False
_FINISHED_AT=0.0
_FAILED_AT=0.0
_BACKEND_LATENCY_MS=None
_SUBSCRIBERS={}

def record_backend_latency(elapsed_ms:int):
    global _BACKEND_LATENCY_MS
    with _LOCK:
        _BACKEND_LATENCY_MS=max(0,elapsed_ms)

def subscribe(loop):
    """One notification queue per authenticated SSE connection."""
    queue=asyncio.Queue(maxsize=1)
    token=uuid4().hex
    with _LOCK:_SUBSCRIBERS[token]=(loop,queue)
    return token,queue

def unsubscribe(token):
    with _LOCK:_SUBSCRIBERS.pop(token,None)

def _notify():
    with _LOCK:subscribers=list(_SUBSCRIBERS.values())
    for loop,queue in subscribers:
        try:
            loop.call_soon_threadsafe(
                lambda q=queue: q.put_nowait(True) if not q.full() else None
            )
        except RuntimeError:
            pass  # A disconnected client's loop has already stopped.

def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def event(state:str,description:str="",task_id:str|None=None):
    with _LOCK:
        _EVENTS.appendleft({"ts":utc_now(),"state":state,"description":description[:100],
                            "task_id":task_id})
    _notify()

@contextmanager
def operation(state:str,description:str=""):
    task_id=uuid4().hex
    global _FINISHED_AT,_FAILED_AT
    with _LOCK:
        _JOBS[task_id]={"state":state,"description":description[:100],"started":monotonic()}
    event(state,description,task_id)
    try:
        yield task_id
    except BaseException:
        with _LOCK:
            _JOBS.pop(task_id,None)
        with _LOCK:_FAILED_AT=monotonic()
        event("attention","Операция завершилась с ошибкой",task_id)
        raise
    else:
        with _LOCK:
            _JOBS.pop(task_id,None)
            _FINISHED_AT=monotonic()
        event("completed","Операция завершена",task_id)

def cloud_request_begin(model:str):
    with _LOCK:
        _CLOUD["active_requests"]=_CLOUD.get("active_requests",0)+1
        _CLOUD["requests_count"]+=1
        _CLOUD["model_id"]=model
    return monotonic()

def cloud_request_end(start:float,*,http_status:int|None=None,
                      reason:str|None=None,usage:dict|None=None):
    elapsed=round((monotonic()-start)*1000)
    with _LOCK:
        _CLOUD["active_requests"]=max(0,_CLOUD.get("active_requests",0)-1)
        _CLOUD["latency_ms"]=elapsed
        _CLOUD["last_http_status"]=http_status
        if reason:
            _CLOUD["last_error"]=reason[:100]
            _CLOUD["state"]=_classify_error(http_status,reason)
        else:
            _CLOUD["last_error"]=None
            _CLOUD["state"]="connected"
            _CLOUD["last_success_at"]=utc_now()
            if usage and isinstance(usage,dict):
                # Tokens only when explicitly returned by the provider.
                _CLOUD["token_usage"]={key:usage.get(key) for key in
                    ("prompt_tokens","completion_tokens","total_tokens")
                    if isinstance(usage.get(key),int)}
        # No imaginary prices or currency conversions.
        _CLOUD["cost_rub"]=None
    _notify()

def _classify_error(status:int|None,reason:str):
    if status in (401,403):return "auth_error"
    if status==402:return "insufficient_balance"
    if status==429:return "rate_limited"
    if reason=="timeout":return "timeout"
    if status in (500,502,503,504):return "degraded"
    return "unreachable"

def status_snapshot(*,cloud_configured:bool,model:str|None=None):
    with _LOCK:
        jobs=list(_JOBS.values())
        if jobs:
            order=["executing","verifying","studying","researching","reasoning",
                   "memorizing","linking"]
            state=next((x for x in order if any(j["state"]==x for j in jobs)),
                       jobs[0]["state"])
            description=next((j["description"] for j in jobs if j["state"]==state),"")
        elif _FAILED_AT and monotonic()-_FAILED_AT<12 and _FAILED_AT>=_FINISHED_AT:
            state="attention"
            description="Последняя задача завершилась ошибкой"
        elif _FINISHED_AT and monotonic()-_FINISHED_AT<6:
            state="completed"
            description="Операция завершена"
        elif cloud_configured and _CLOUD["state"] in ("auth_error","insufficient_balance","rate_limited"):
            state="attention"
            description="Cloud.ru требует проверки настроек или ограничений"
        elif cloud_configured and _CLOUD["state"] in ("unreachable","timeout"):
            state="disconnected"
            description="Нет связи с Cloud.ru"
        else:
            state="ready"
            description="Ожидает запроса"
        cloud=dict(_CLOUD)
        network=dict(_NETWORK)
        server_latency=_BACKEND_LATENCY_MS
        events=list(_EVENTS)[:8]
    if not cloud_configured:
        cloud.update(state="unknown",last_error="Модель или API-ключ не настроены",
                     latency_ms=None,model_id=model or None)
    elif cloud.get("model_id") is None:
        cloud["model_id"]=model or None
    return {"event":"runtime_status","ts":utc_now(),
            "sayuri":{"state":state,"active_jobs":len(jobs),
                      "description":description,"progress_percent":None},
            "network":{"state":network["state"],"backend":"online",
                       "latency_ms":network["latency_ms"],
                       "server_latency_ms":server_latency,
                       "probe_target":"github.com",
                       "last_success_at":network["last_success_at"],
                       "failure_reason":network["failure_reason"]},
            "cloud_ru":cloud,
            "recent_events":events,
            "features":{"websocket":False,"sse":True,
                        "knowledge_graph":False,"document_indexer":False}}

async def _probe_network():
    global _NET_NEXT,_NET_PROBING
    with _LOCK:
        if _NET_PROBING or monotonic()<_NET_NEXT:return
        _NET_PROBING=True
        _NET_NEXT=monotonic()+25
    begin=monotonic()
    try:
        async with httpx.AsyncClient(timeout=4,follow_redirects=False) as client:
            response=await client.head("https://github.com/")
        # Even 4xx means an HTTP response from outside; distinguish reachability from success.
        ok=response.status_code<500
        with _LOCK:
            _NETWORK.update(state="online" if ok else "degraded",
                            latency_ms=round((monotonic()-begin)*1000),
                            last_success_at=utc_now() if ok else _NETWORK["last_success_at"],
                            failure_reason=None if ok else "HTTP "+str(response.status_code))
    except httpx.TimeoutException:
        with _LOCK:_NETWORK.update(state="offline",latency_ms=None,failure_reason="timeout")
    except httpx.HTTPError:
        with _LOCK:_NETWORK.update(state="offline",latency_ms=None,failure_reason="unreachable")
    finally:
        with _LOCK:_NET_PROBING=False
        _notify()

async def _probe_cloud(key:str,base:str,model:str):
    global _CLOUD_NEXT,_CLOUD_PROBING
    if not (key and base and model):return
    with _LOCK:
        if _CLOUD_PROBING or monotonic()<_CLOUD_NEXT:return
        _CLOUD_PROBING=True
        _CLOUD_NEXT=monotonic()+30
    start=monotonic()
    try:
        async with httpx.AsyncClient(timeout=5,follow_redirects=False) as client:
            response=await client.get(base.rstrip("/")+"/models",
                headers={"Authorization":"Bearer "+key})
        status=response.status_code
        # A healthy /models endpoint does not prove the selected model exists.
        exists=None
        if status==200:
            try:
                listing=response.json().get("data",[])
                ids={item.get("id") for item in listing if isinstance(item,dict)}
                if isinstance(listing,list) and ids:
                    exists=(model in ids)
            except (ValueError,TypeError,AttributeError):
                exists=None
        with _LOCK:
            _CLOUD["model_id"]=model
            _CLOUD["latency_ms"]=round((monotonic()-start)*1000)
            _CLOUD["last_http_status"]=status
            if status==200 and exists is False:
                _CLOUD["state"]="degraded"
                _CLOUD["last_error"]="Выбранная модель отсутствует в списке Cloud.ru"
            elif status==200 and exists is None:
                _CLOUD["state"]="unknown"
                _CLOUD["last_error"]="Не удалось проверить доступность модели"
            else:
                _CLOUD["state"]="connected" if status==200 else _classify_error(status,"http")
                _CLOUD["last_error"]=None if status==200 else "HTTP "+str(status)
            if status==200 and exists is True:_CLOUD["last_success_at"]=utc_now()
    except httpx.TimeoutException:
        with _LOCK:_CLOUD.update(state="timeout",last_error="timeout",last_http_status=None)
    except httpx.HTTPError:
        with _LOCK:_CLOUD.update(state="unreachable",last_error="unreachable",last_http_status=None)
    finally:
        with _LOCK:_CLOUD_PROBING=False
        _notify()

async def refresh_probes(*,key:str,base:str,model:str):
    # Independent failures: local backend online never means the Internet is online.
    await asyncio.gather(_probe_network(),_probe_cloud(key,base,model))
