import asyncio
import os
import time
from dataclasses import dataclass, field

from fastapi import FastAPI, Header, HTTPException, Request

from webhook_relay.security.hmac_signer import verify

app = FastAPI(title="Mock Receiver")

SECRET = os.environ.get("MOCK_RECEIVER_SECRET", "demo-secret")


@dataclass
class State:
    mode: str = "ok"  # ok | fail | timeout | reject
    received: list[dict] = field(default_factory=list)
    seen_idempotency_keys: set[str] = field(default_factory=set)


state = State()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def receive_webhook(
    request: Request,
    x_signature: str = Header(...),
    x_timestamp: str = Header(...),
    x_idempotency_key: str = Header(...),
):
    raw_body = await request.body()

    if not verify(SECRET, x_timestamp, raw_body, x_signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    is_duplicate = x_idempotency_key in state.seen_idempotency_keys
    state.seen_idempotency_keys.add(x_idempotency_key)
    state.received.append(
        {
            "idempotency_key": x_idempotency_key,
            "duplicate": is_duplicate,
            "body": raw_body.decode(),
            "received_at": time.time(),
        }
    )

    if state.mode == "timeout":
        await asyncio.sleep(15)

    if state.mode == "fail":
        raise HTTPException(status_code=500, detail="simulated failure")

    if state.mode == "reject":
        raise HTTPException(status_code=400, detail="simulated client error")

    return {"status": "received", "duplicate": is_duplicate}


@app.post("/_control/mode/{mode}")
async def set_mode(mode: str):
    if mode not in ("ok", "fail", "timeout", "reject"):
        raise HTTPException(status_code=400, detail="mode must be ok, fail, timeout or reject")
    state.mode = mode
    return {"mode": state.mode}


@app.get("/_control/received")
async def get_received():
    return state.received


@app.post("/_control/reset")
async def reset():
    state.received.clear()
    state.seen_idempotency_keys.clear()
    state.mode = "ok"
    return {"status": "reset"}
