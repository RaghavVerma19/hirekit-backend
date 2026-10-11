"""External LaTeX -> PDF compile client (no local TeXLive).

Supports managed endpoints with a single generic contract:
  POST {LATEX_API_URL}  Authorization: Bearer {LATEX_API_KEY}
  JSON: {"source": "<tex>", "engine": "pdflatex"}
Known-compatible: FormaTeX POST /v1/compile/sync, LaTeX++ POST /v1/compile,
self-hosted tex-to-pdf-api /v2/compile/sync.

Response handling (in order):
  1. raw application/pdf bytes -> success
  2. JSON {pdf: base64, log/errors} -> decode
  3. JSON {pdf_url} -> download via httpx
  4. else -> failure with log excerpt

When LATEX_API_URL is empty -> explicit not-configured failure (no fake URL).
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any, Dict, Optional

import structlog

from app.core.config import settings

logger = structlog.get_logger()


async def compile_latex_source(source: str, engine: Optional[str] = None) -> Dict[str, Any]:
    """Compile LaTeX source via external API. Returns {success, pdf_bytes?, log, engine}."""
    eng = engine or settings.LATEX_ENGINE or "pdflatex"
    if not settings.LATEX_API_URL:
        return {
            "success": False,
            "pdf_bytes": None,
            "log": "LATEX_API_URL is not configured. Set LATEX_API_URL + LATEX_API_KEY to enable exact PDF compile.",
            "engine": eng,
            "not_configured": True,
        }
    if not source or "\\begin{document}" not in source or "\\end{document}" not in source:
        return {"success": False, "pdf_bytes": None, "log": "Refusing to compile: missing \\begin{document}/\\end{document}.", "engine": eng}

    import httpx

    headers = {"Content-Type": "application/json"}
    if settings.LATEX_API_KEY:
        headers["Authorization"] = f"Bearer {settings.LATEX_API_KEY}"
        headers["X-API-Key"] = settings.LATEX_API_KEY

    payload = {"source": source, "engine": eng, "timeout": settings.LATEX_TIMEOUT_SECONDS}
    # Render Free cold-start: first request after 15min idle can take ~60s
    # and may return a loading page / 502. Retry once with extended timeout.
    attempts = 2
    resp = None
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            wait = float(settings.LATEX_TIMEOUT_SECONDS + 10 + (60 if attempt > 0 else 0))
            async with httpx.AsyncClient(timeout=wait) as client:
                resp = await client.post(settings.LATEX_API_URL, json=payload, headers=headers)
            # Render spin-up page is HTML, not PDF/JSON — treat as retryable
            body_start = (resp.text or "")[:200].lower()
            if resp.status_code in (502, 503) or ("render" in body_start and "spin" in body_start):
                if attempt < attempts - 1:
                    import asyncio as _aio

                    await _aio.sleep(8)
                    continue
            break
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                import asyncio as _aio

                await _aio.sleep(5)
                continue
            logger.warning("latex_compile_request_failed", error=str(exc))
            return {"success": False, "pdf_bytes": None, "log": f"Compile request failed: {exc}", "engine": eng}
    if resp is None:
        logger.warning("latex_compile_request_failed", error=str(last_exc))
        return {"success": False, "pdf_bytes": None, "log": f"Compile request failed: {last_exc}", "engine": eng}

    ctype = (resp.headers.get("content-type") or "").lower()
    # 1. raw PDF
    if resp.status_code == 200 and ("application/pdf" in ctype or resp.content[:4] == b"%PDF"):
        return {"success": True, "pdf_bytes": bytes(resp.content), "log": "compile ok (raw pdf)", "engine": eng}

    # 2/3. JSON envelope
    try:
        data = resp.json()
    except Exception:
        return {"success": False, "pdf_bytes": None, "log": f"Compile failed HTTP {resp.status_code}: {(resp.text or '')[:2000]}", "engine": eng}

    if isinstance(data, dict):
        # error envelope
        log = str(data.get("log") or data.get("error") or data.get("message") or data.get("detail") or "")
        errors = data.get("errors")
        if errors:
            log = (log + "\n" + str(errors))[:4000]
        pdf_b64 = data.get("pdf") or data.get("pdf_base64") or data.get("data")
        if isinstance(pdf_b64, str) and len(pdf_b64) > 100:
            try:
                raw = base64.b64decode(pdf_b64)
                if raw[:4] == b"%PDF":
                    return {"success": True, "pdf_bytes": raw, "log": log or "compile ok (base64)", "engine": eng}
            except Exception as exc:
                log += f"\nbase64_decode_failed: {exc}"
        pdf_url = data.get("pdf_url") or data.get("url")
        if isinstance(pdf_url, str) and pdf_url.startswith("http") and resp.status_code < 300:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client2:
                    dl = await client2.get(pdf_url)
                    if dl.status_code == 200 and dl.content[:4] == b"%PDF":
                        return {"success": True, "pdf_bytes": bytes(dl.content), "log": log or "compile ok (url)", "engine": eng}
            except Exception as exc:
                log += f"\npdf_url_download_failed: {exc}"
        status = str(data.get("status") or "").lower()
        if resp.status_code < 300 and status in ("success", "ok", "completed"):
            return {"success": True, "pdf_bytes": None, "log": log or "compile reported success (no pdf payload)", "engine": eng}
        return {"success": False, "pdf_bytes": None, "log": log[:4000] or f"Compile failed HTTP {resp.status_code}", "engine": eng}

    return {"success": False, "pdf_bytes": None, "log": f"Compile failed HTTP {resp.status_code}: {str(data)[:2000]}", "engine": eng}


def source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
