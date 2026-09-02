# HireKit — FastAPI Enterprise Placement Backend

Modern, async, production-grade backend engine for the **HireKit University Campus Placement & Career Platform**. Built with **FastAPI**, **PostgreSQL 16**, **Redis 7**, **SQLAlchemy 2.0 (async)**, and **Gemini 2.0 AI ATS scoring**.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│               HireKit Next.js Frontend                 │
│               http://localhost:3000                    │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP / JSON & WebSocket (JWT)
┌──────────────────────────▼─────────────────────────────┐
│               FastAPI Backend (Port 8000)              │
│                                                        │
│ • /api/v1/auth          • /api/v1/profile              │
│ • /api/v1/resumes       • /api/v1/jobs                 │
│ • /api/v1/applications  • /api/v1/dashboard            │
│ • /api/v1/feed          • /api/v1/notifications        │
│ • /api/v1/interviews    • /api/v1/admin                │
│ • /api/v1/search        • /api/v1/ws/connect           │
└──────────────┬───────────────────────────┬─────────────┘
               │                           │
┌──────────────▼──────────┐ ┌──────────────▼─────────────┐
│  PostgreSQL 16 (DB)     │ │   Redis 7 (Cache & ZSET)   │
│                         │ │                            │
│ • User & Refresh Tokens │ │ • ATS Content-Hash Cache   │
│ • Profile & Marksheets  │ │ • Distributed Locks        │
│ • Resumes & Scores      │ │ • Leaderboard ZSET         │
│ • Drives & Applications │ │ • Pub/Sub WebSocket Alert  │
│ • Audit Logs            │ │ • Rate Limiting Counters   │
└─────────────────────────┘ └────────────────────────────┘
```

---

## Key Features

1. **Enterprise Authentication & Session Security**:
   - Argon2id password hashing with dummy evaluation to prevent timing attacks.
   - Short-lived PyJWT access tokens paired with rotating HttpOnly refresh tokens in the database.
   - 30-second multi-tab refresh grace period preventing false session invalidations.
   - Non-HttpOnly CSRF double-submit protection.

2. **Profile Engine & S3 Upload Pipeline**:
   - Complete normalized schema for Education, Experience, Responsibilities, Normalized Skills, Projects, Accomplishments (8 subtypes), Guardians, and Social Links.
   - Anti-IDOR authorization checks on all sub-resource mutations (returns 404 to prevent ID existence probing).
   - Strict field whitelisting to eliminate mass-assignment privilege escalation.
   - Presigned S3/R2 direct upload URLs with Content-Type allowlisting and Pillow WebP thumbnailing.

3. **Resume Studio & Gemini AI ATS Scoring**:
   - Auto-populates resume sections from the candidate's verified profile.
   - SHA-256 content-hash fingerprinting caches ATS evaluations in Redis ($0 cost and 0ms latency on repeated checks).
   - Distributed NX locks prevent duplicate concurrent AI evaluations (`429`).
   - Optimistic concurrency locking (`409 Conflict`) stops multi-tab edit overwrites.
   - Asynchronous PDF generation in background workers.

4. **Batch Leaderboards & Percentile Scoring**:
   - Redis Sorted Set (`ZSET`) powers instant rank and percentile calculations.
   - Reconciled hourly via background cron jobs.

5. **Campus Placement Drives & 1-Click Apply**:
   - Real-time eligibility evaluation based on student CGPA and department requirements.
   - Idempotent 1-click apply guarantees duplicate submissions return existing application data with `201`.
   - Complete stage timeline auditing (`APPLIED`, `SHORTLISTED`, `INTERVIEW_SCHEDULED`, `OFFERED`, `WITHDRAWN`).

6. **Real-time Notifications & Authenticated WebSockets**:
   - Pre-handshake JWT verification for WebSockets.
   - Redis Pub/Sub multi-replica fan-out streams instant interview and placement alerts.

7. **University TPO & Admin Portal**:
   - Bulk student marksheet verification with structured audit logging.
   - Bulk application status transitions with automated candidate alerts.
   - Campus-wide placement analytics (placement rate %, average/highest CTC, active drives).

---

## Local Development Setup

### 1. Prerequisites
- **Python 3.12+**
- **Docker & Docker Compose** (for PostgreSQL & Redis)

### 2. Start PostgreSQL & Redis
```bash
docker compose up -d
```

### 3. Setup Python Virtual Environment
```bash
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"
```

### 4. Run Database Migrations
```bash
alembic upgrade head
```

### 5. Start the FastAPI Development Server
```bash
uvicorn app.main:app --reload --port 8000
```
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc API Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 6. Start the Background Worker (Optional)
```bash
arq app.workers.worker.WorkerSettings
```

---

## Running Automated Tests
Run the comprehensive async test suite (over SQLite in-memory and Mock Redis):
```bash
pytest -v
```

---

## Production Docker Deployment
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
