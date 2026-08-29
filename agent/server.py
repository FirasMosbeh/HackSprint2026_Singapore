from __future__ import annotations

import asyncio
import threading
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .models import Audition, AuditionRequest
from .orchestrator import AuditionOrchestrator

app = FastAPI(title="Sentrya Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = AuditionOrchestrator()


class StatusResponse(BaseModel):
    id: str
    status: str


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auditions", response_model=Audition)
def start_audition(request: AuditionRequest, background_tasks: BackgroundTasks) -> Audition:
    audition = orchestrator.create_audition(request.requirement, request.candidates)
    background_tasks.add_task(_spawn_runner, audition.id)
    return audition


@app.get("/api/auditions/{audition_id}", response_model=Audition)
def get_audition(audition_id: str) -> Audition:
    audition = orchestrator.store.get(audition_id)
    if not audition:
        raise HTTPException(status_code=404, detail="audition not found")
    return audition


@app.get("/api/auditions/{audition_id}/status", response_model=StatusResponse)
def get_status(audition_id: str) -> StatusResponse:
    audition = orchestrator.store.get(audition_id)
    if not audition:
        raise HTTPException(status_code=404, detail="audition not found")
    return StatusResponse(id=audition.id, status=audition.status.value)


@app.delete("/api/auditions/{audition_id}")
def cancel_audition(audition_id: str) -> JSONResponse:
    orchestrator.store.cancel(audition_id)
    return JSONResponse({"ok": True})


@app.get("/api/mode")
def mode() -> dict[str, Any]:
    return {"backend": "agent", "testing": "enabled"}


def _spawn_runner(audition_id: str) -> None:
    def _run() -> None:
        asyncio.run(orchestrator.run_audition(audition_id))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def main() -> int:
    import uvicorn

    uvicorn.run("agent.server:app", host="0.0.0.0", port=8000, reload=False)
    return 0
