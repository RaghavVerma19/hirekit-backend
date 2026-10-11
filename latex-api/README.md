# HireKit LaTeX Compile API (free, Render-ready)

Minimal exact-PDF compiler for single-column resumes. Uses **Tectonic** (not TeXLive-full)
so it fits Render Free (0.1 CPU / 512MB).

## Deploy on Render (Blueprint, subfolder)

1. Push this repo (includes `render.yaml` at backend root with `rootDir: latex-api`).
2. Render → New → Blueprint → select repo → service `hirekit-latex-compile` (Free, Docker).
3. Copy URL, e.g. `https://hirekit-latex-compile.onrender.com`, and generated `API_KEY`.

## Configure HireKit backend `.env`

```env
LATEX_API_URL=https://hirekit-latex-compile.onrender.com/compile/sync
LATEX_API_KEY=<same as Render API_KEY>
LATEX_ENGINE=pdflatex
LATEX_TIMEOUT_SECONDS=60
```

## Test

```bash
curl -X POST http://localhost:10000/compile/sync \
  -H "Content-Type: application/json" \
  -d '{"source":"\\documentclass{article}\\begin{document}Hi\\end{document}"}' \
  --output test.pdf
```

## Notes

- v1: single-column only. `multicols/minipage` rejected with clear log.
- Cold start on Free: first request after 15min idle takes ~60s; warm ~2-5s.
- Auth: set `API_KEY` env to require `Authorization: Bearer <key>` or `X-API-Key`.
