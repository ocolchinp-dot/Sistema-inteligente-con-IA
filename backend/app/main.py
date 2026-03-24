from __future__ import annotations

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .agent import run_agent
from .schemas import AnalyzeResponse

app = FastAPI(title="Lab Result Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_document(file: UploadFile = File(...)) -> AnalyzeResponse:
    file_bytes = await file.read()
    return run_agent(file_bytes=file_bytes, filename=file.filename or "unknown", content_type=file.content_type)
