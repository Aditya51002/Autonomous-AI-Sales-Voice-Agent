"""HTTP API: calls, documents and lead data.

Run from the project root:  uvicorn apps.api.main:app --port 8000
"""

import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel, Field

from apps.api import knowledge
from apps.api.knowledge import trusted_origin
from packages.core.config import DISPATCH_NAME, Settings, get_settings
from packages.core.leads.store import LeadStore


class CallRequest(BaseModel):
    consent: bool = False
    # Random id this browser got on an earlier call. Not a name or phone number.
    lead_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class CallResponse(BaseModel):
    url: str
    room: str
    token: str
    lead_id: str


def create_call(request: CallRequest, settings: Settings) -> CallResponse:
    if not request.consent:
        raise HTTPException(400, "Consent to an AI-handled, transcribed call is required.")
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise HTTPException(503, "LiveKit is not configured. See .env.example.")

    room = f"call-{uuid.uuid4().hex}"
    identity = f"prospect-{uuid.uuid4().hex[:8]}"
    lead_id = request.lead_id or uuid.uuid4().hex
    # Short-lived, limited to one new room, and it dispatches the agent into it.
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_ttl(timedelta(minutes=10))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_sources=["microphone"],
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=DISPATCH_NAME, metadata=json.dumps({"lead_id": lead_id})
                    )
                ]
            )
        )
        .to_jwt()
    )
    return CallResponse(url=settings.livekit_url, room=room, token=token, lead_id=lead_id)


def _warm_up() -> None:
    try:
        knowledge.get_knowledge()
        logging.getLogger("uvicorn.error").info("knowledge search is ready")
    except Exception:
        logging.getLogger("uvicorn.error").exception("knowledge search failed to load")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load the embedding model before the first call, without delaying startup.
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="AI Sales Voice Agent API", lifespan=lifespan)
app.include_router(knowledge.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# No login or rate limit yet: run on localhost only until Phase 5.
@app.post("/calls")
def post_call(
    request: CallRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> CallResponse:
    return create_call(request, settings)


def get_lead_store(settings: Annotated[Settings, Depends(get_settings)]) -> LeadStore:
    return LeadStore(settings.leads_db)


@app.delete("/leads/{lead_id}", status_code=204, dependencies=[Depends(trusted_origin)])
def forget_lead(
    lead_id: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    store: Annotated[LeadStore, Depends(get_lead_store)],
) -> None:
    """Erase everything stored about this caller."""
    store.delete_lead(lead_id)
