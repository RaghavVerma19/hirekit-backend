"""HireKit LaTeX compile micro-service (Render Free friendly).

Minimal single-column resume compiler using Tectonic (~100MB) instead of
TeXLive-full (~4GB) so it fits Render Free (0.1 CPU / 512MB RAM).

Contract (matches hirekit-backend latex_compile_service.py):
  POST /compile/sync  JSON {"source": "<tex>", "engine": "pdflatex", "timeout": 60}
    -> 200 application/pdf (raw bytes) on success
    -> 4xx/422 {"log": "<compiler output>"} on failure
  GET /health -> {"ok": true}

Auth: if API_KEY env is set, requires Authorization: Bearer <key>
      or X-API-Key: <key>. Otherwise open.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

API_KEY = os.environ.get("API_KEY", "").strip()
COMPILE_TIMEOUT = int(os.environ.get("COMPILE_TIMEOUT", "25"))

app = FastAPI(title="HireKit LaTeX Compile API", version="1.0.0")


class CompileIn(BaseModel):
    source: str = Field(..., min_length=20, max_length=400_000)
    engine: str = Field("pdflatex", max_length=20)
    timeout: Optional[int] = None


def _authorized(authorization: Optional[str], x_api_key: Optional[str]) -> bool:
    if not API_KEY:
        return True
    if x_api_key and x_api_key.strip() == API_KEY:
        return True
    if authorization and authorization.strip() == f"Bearer {API_KEY}":
        return True
    # allow raw key without Bearer prefix
    if authorization and authorization.strip() == API_KEY:
        return True
    return False


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "engine": "tectonic", "auth": bool(API_KEY)}


@app.post("/compile/sync")
async def compile_sync(
    payload: CompileIn,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Response:
    if not _authorized(authorization, x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key.")

    source = payload.source
    if "\\begin{document}" not in source or "\\end{document}" not in source:
        return JSONResponse(
            status_code=400,
            content={"log": "Refusing to compile: missing \\begin{document}/\\end{document}."},
        )
    # v1 scope: single column only — reject obvious multi-column attempts early
    lowered = source.lower()
    if any(token in lowered for token in ("\\begin{multicols", "\\begin{minipage", "multicol")):
        return JSONResponse(
            status_code=422,
            content={"log": "Multi-column layouts are deferred in v1 (single-column only)."},
        )

    timeout = payload.timeout or COMPILE_TIMEOUT
    timeout = max(5, min(60, int(timeout)))
    tectonic = shutil.which("tectonic")
    if not tectonic:
        return JSONResponse(status_code=500, content={"log": "tectonic binary not installed."})

    tmpdir = tempfile.mkdtemp(prefix="texcompile_")
    try:
        tex_path = Path(tmpdir) / "main.tex"
        tex_path.write_text(source, encoding="utf-8")
        outdir = Path(tmpdir) / "out"
        outdir.mkdir(parents=True, exist_ok=True)

        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(
                [tectonic, "-X", "compile", str(tex_path), "--outdir", str(outdir)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            return JSONResponse(status_code=422, content={"log": f"Compile timed out after {timeout}s."})

        pdf_path = outdir / "main.pdf"
        if proc.returncode == 0 and pdf_path.exists():
            pdf_bytes = pdf_path.read_bytes()
            if pdf_bytes[:4] == b"%PDF":
                return Response(content=pdf_bytes, media_type="application/pdf")
            return JSONResponse(status_code=422, content={"log": "Compiler produced invalid PDF."})

        log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-4000:]
        return JSONResponse(status_code=422, content={"log": log or "Compile failed."})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
