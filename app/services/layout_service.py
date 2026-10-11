"""Single-column layout-aware extraction for Resume Edit Studio.

Replaces pypdf-only `extract_text()` (which drops geometry/fonts/rules)
with PyMuPDF span-level geometry so generated LaTeX preserves:
  margins / page size / font sizes / bold-italic / colors / rules / links / bullets / spacing.

v1 scope: single-column only. Multi-column/sidebar detected -> flagged,
caller may still produce a single-column fallback.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional


def _pt_to_in(pt: float) -> float:
    return round(pt / 72.0, 3)


def _int_to_hex(color_int: int) -> str:
    try:
        r = (color_int >> 16) & 255
        g = (color_int >> 8) & 255
        b = color_int & 255
        return f"{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "000000"


def extract_layout(pdf_bytes: bytes) -> Dict[str, Any]:
    """Extract single-column layout JSON from PDF bytes.

    Returns dict with keys:
      pages, page_width_pt/height_pt, margins_in, body_size, name_size,
      colors, has_rule, links, blocks, is_multicolumn, warnings
    Never raises on missing PyMuPDF — falls back to pypdf text-only stub.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as exc:  # pragma: no cover - dep missing
        return _fallback_layout(pdf_bytes, warning=f"pymupdf_unavailable: {exc}")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        return _fallback_layout(pdf_bytes, warning=f"pdf_open_failed: {exc}")

    try:
        if len(doc) == 0:
            return _fallback_layout(pdf_bytes, warning="empty_pdf")
        if len(doc) > 10:
            raise ValueError("Resume PDF exceeds maximum allowed page count (10 pages).")

        pages: List[Dict[str, Any]] = []
        all_sizes: List[float] = []
        all_colors: Counter = Counter()
        all_x0: List[float] = []
        all_x1: List[float] = []
        page_w = page_h = 0.0
        has_rule = False
        links: List[Dict[str, str]] = []
        is_multicolumn = False
        warnings: List[str] = []

        for pno, page in enumerate(doc):
            rect = page.rect
            page_w, page_h = float(rect.width), float(rect.height)
            d = page.get_text("dict")
            spans_out: List[Dict[str, Any]] = []
            for block in d.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = (span.get("text") or "").strip()
                        if not text:
                            continue
                        size = float(span.get("size", 10))
                        all_sizes.append(round(size, 1))
                        color_hex = _int_to_hex(int(span.get("color", 0)))
                        if color_hex != "000000":
                            all_colors[color_hex] += 1
                        flags = int(span.get("flags", 0))
                        bbox = span.get("bbox", [0, 0, 0, 0])
                        spans_out.append(
                            {
                                "text": text,
                                "font": span.get("font", ""),
                                "size": round(size, 2),
                                "bold": bool(flags & 16),
                                "italic": bool(flags & 2),
                                "color": color_hex,
                                "bbox": [round(float(v), 1) for v in bbox],
                                "origin": [round(float(span.get("origin", [0, 0])[0]), 1),
                                           round(float(span.get("origin", [0, 0])[1]), 1)] if span.get("origin") else [0, 0],
                            }
                        )
                        all_x0.append(float(bbox[0]))
                        all_x1.append(float(bbox[2]))

            # drawings -> horizontal rules
            try:
                for drawing in page.get_drawings():
                    r = drawing.get("rect")
                    if r is None:
                        continue
                    w = abs(float(r.x1) - float(r.x0))
                    h = abs(float(r.y1) - float(r.y0))
                    if w > 200 and h < 3:
                        has_rule = True
            except Exception:
                pass

            # links
            try:
                for ln in page.get_links():
                    uri = (ln.get("uri") or "").strip()
                    if uri:
                        links.append({"page": pno, "uri": uri})
            except Exception:
                pass

            # crude 2-column detection: bimodal x0 distribution with wide gap
            if spans_out:
                xs = sorted(s["bbox"][0] for s in spans_out if len(s["text"]) > 2)
                if len(xs) > 10:
                    mid = (min(xs) + max(xs)) / 2
                    left = sum(1 for x in xs if x < mid - 60)
                    right = sum(1 for x in xs if x > mid + 60)
                    if left > 5 and right > 5:
                        is_multicolumn = True

            pages.append({"page": pno, "width_pt": round(page_w, 1), "height_pt": round(page_h, 1), "spans": spans_out})

        if is_multicolumn:
            warnings.append("multi_column_detected_v1_single_column_fallback")

        # margins from content bbox
        if all_x0 and all_x1 and page_w:
            left_in = _pt_to_in(min(all_x0))
            right_in = _pt_to_in(max(0.0, page_w - max(all_x1)))
            # top/bottom from first/last span y
            all_y0: List[float] = []
            all_y1: List[float] = []
            for p in pages:
                for s in p["spans"]:
                    all_y0.append(s["bbox"][1])
                    all_y1.append(s["bbox"][3])
            top_in = _pt_to_in(min(all_y0)) if all_y0 else 0.6
            bottom_in = _pt_to_in(max(0.0, page_h - max(all_y1))) if all_y1 else 0.6
            # clamp to sane 0.3..1.2in
            def _clamp(v: float) -> float:
                return max(0.3, min(1.2, round(v, 2)))
            margins_in = {"left": _clamp(left_in), "right": _clamp(right_in), "top": _clamp(top_in), "bottom": _clamp(bottom_in)}
        else:
            margins_in = {"left": 0.6, "right": 0.6, "top": 0.6, "bottom": 0.6}

        body_size = Counter(all_sizes).most_common(1)[0][0] if all_sizes else 10.0
        name_size = max(all_sizes) if all_sizes else 16.0

        return {
            "engine": "pymupdf",
            "pages": pages,
            "page_count": len(pages),
            "page_width_pt": round(page_w, 1),
            "page_height_pt": round(page_h, 1),
            "margins_in": margins_in,
            "body_size": float(body_size),
            "name_size": float(name_size),
            "colors": dict(all_colors.most_common(8)),
            "has_rule": has_rule,
            "links": links[:50],
            "is_multicolumn": is_multicolumn,
            "warnings": warnings,
        }
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _fallback_layout(pdf_bytes: bytes, warning: str) -> Dict[str, Any]:
    """Text-only fallback when PyMuPDF unavailable — explicit, no invented geometry."""
    text = ""
    try:
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        text = ""
    return {
        "engine": "pypdf-text-only",
        "pages": [],
        "page_count": 0,
        "page_width_pt": 595.0,
        "page_height_pt": 842.0,
        "margins_in": {"left": 0.6, "right": 0.6, "top": 0.6, "bottom": 0.6},
        "body_size": 10.0,
        "name_size": 16.0,
        "colors": {},
        "has_rule": False,
        "links": [],
        "is_multicolumn": False,
        "warnings": [warning, "geometry_fallback_used"],
        "raw_text_hint": text[:2000],
    }


def layout_to_geometry_args(layout: Optional[Dict[str, Any]]) -> str:
    """Convert layout margins to \\geometry args string."""
    m = (layout or {}).get("margins_in") or {"left": 0.6, "right": 0.6, "top": 0.6, "bottom": 0.6}
    try:
        return f"left={float(m.get('left', 0.6))}in,right={float(m.get('right', 0.6))}in,top={float(m.get('top', 0.6))}in,bottom={float(m.get('bottom', 0.6))}in"
    except Exception:
        return "margin=0.6in"
