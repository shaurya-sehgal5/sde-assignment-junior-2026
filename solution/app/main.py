import json

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from app.services.webhooks import verify_signature, process_webhook

app = FastAPI(title="Durable Campaign Dispatcher")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/telephony")
async def telephony_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-AU-Signature")

    if not verify_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        result = process_webhook(payload, raw_body)
        return JSONResponse(result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
