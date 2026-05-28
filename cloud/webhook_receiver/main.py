import json
import os
import logging
from fastapi import FastAPI, HTTPException, Request
from google.cloud import pubsub_v1

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
publisher = pubsub_v1.PublisherClient()

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
PROJECT_ID = os.environ["PUBSUB_PROJECT_ID"]
TOPIC_ID = "tradingview-alerts"


@app.post("/alert")
async def receive_alert(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if body.get("secret") != WEBHOOK_SECRET:
        logger.warning("Alert rejected: invalid secret")
        raise HTTPException(status_code=403, detail="Invalid secret")

    payload = {k: v for k, v in body.items() if k != "secret"}
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    data = json.dumps(payload).encode("utf-8")
    future = publisher.publish(topic_path, data)
    future.result()

    logger.info(f"Alert published: {payload.get('symbol')} {payload.get('action')}")
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}
