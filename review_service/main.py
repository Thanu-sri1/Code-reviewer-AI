import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException, Response
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel, Field

from analyzers import analyze_code
from repository_review import RepositoryReviewError, run_repository_review, validate_github_url


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"review-service","message":"%(message)s"}',
)
logger = logging.getLogger("review-service")

app = FastAPI(title="Review Management Service")

def read_config_value(name: str, default: str = "") -> str:
    value = (os.getenv(name) or "").strip().strip("\"'")
    if value:
        return value

    file_path = os.getenv(f"{name}_FILE") or f"/mnt/secrets-store/{name}"
    if os.path.exists(file_path):
        return open(file_path).read().strip().strip("\"'")

    return default


DATABASE_URL = read_config_value("DATABASE_URL", "postgresql://coderaptor:coderaptor@postgres:5432/coderaptor")
AI_SERVICE_URL = read_config_value("AI_SERVICE_URL", "http://ai-service:8003")
REQUEST_COUNT = 0
REQUEST_LATENCY_SECONDS = 0.0
REPOSITORY_REVIEW_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.getenv("REPOSITORY_REVIEW_WORKERS", "2")))
ENQUEUED_REPOSITORY_JOBS: set[str] = set()
REVIEW_MODES = {
    "Security Review",
    "Performance Review",
    "Best Practices Review",
    "DevOps Review",
    "Full Repository Review",
}


@app.middleware("http")
async def track_requests(request, call_next):
    global REQUEST_COUNT, REQUEST_LATENCY_SECONDS
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    REQUEST_COUNT += 1
    REQUEST_LATENCY_SECONDS += elapsed
    logger.info(
        json.dumps(
            {
                "event": "request_completed",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
            }
        )
    )
    return response


@app.get("/health")
def health_check():
    return {"service": "review-service", "status": "ok"}


@app.get("/ready")
def readiness_check():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"service": "review-service", "status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/live")
def liveness_check():
    return {"service": "review-service", "status": "alive"}


@app.get("/metrics")
def prometheus_metrics():
    payload = "\n".join(
        [
            "# HELP review_service_requests_total Total HTTP requests handled by review service.",
            "# TYPE review_service_requests_total counter",
            f"review_service_requests_total {REQUEST_COUNT}",
            "# HELP review_service_request_latency_seconds_total Cumulative request latency.",
            "# TYPE review_service_request_latency_seconds_total counter",
            f"review_service_request_latency_seconds_total {REQUEST_LATENCY_SECONDS:.6f}",
            "",
        ]
    )
    return Response(content=payload, media_type="text/plain; version=0.0.4")


def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS reviews
                   (id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    code TEXT,
                    review_output TEXT,
                    run_output TEXT,
                    fixed_code TEXT,
                    fixed_code_language TEXT NOT NULL DEFAULT 'python',
                    timestamp TEXT)"""
            )
            cur.execute("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS fixed_code_language TEXT NOT NULL DEFAULT 'python'")
            cur.execute(
                """CREATE TABLE IF NOT EXISTS repository_metrics
                   (repository_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
                    filename TEXT,
                    loc INTEGER NOT NULL DEFAULT 0,
                    classes INTEGER NOT NULL DEFAULT 0,
                    functions INTEGER NOT NULL DEFAULT 0,
                    variables INTEGER NOT NULL DEFAULT 0,
                    imports INTEGER NOT NULL DEFAULT 0,
                    comment_percentage NUMERIC NOT NULL DEFAULT 0,
                    cyclomatic_complexity INTEGER NOT NULL DEFAULT 0,
                    maintainability_score NUMERIC NOT NULL DEFAULT 0,
                    technical_debt_score NUMERIC NOT NULL DEFAULT 0,
                    code_quality_score NUMERIC NOT NULL DEFAULT 0,
                    variable_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
                    function_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS memory_analysis
                   (repository_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
                    score NUMERIC NOT NULL DEFAULT 0,
                    patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
                    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS performance_analysis
                   (repository_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
                    score NUMERIC NOT NULL DEFAULT 0,
                    nested_loops INTEGER NOT NULL DEFAULT 0,
                    patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
                    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS health_scores
                   (repository_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
                    score NUMERIC NOT NULL DEFAULT 0,
                    rating TEXT NOT NULL,
                    components JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS optimization_recommendations
                   (id SERIAL PRIMARY KEY,
                    repository_id TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'medium',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS repository_review_jobs
                   (id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    repository_url TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    result JSONB,
                    error TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
            )
        conn.commit()


def get_db_connection():
    for _ in range(10):
        try:
            return psycopg2.connect(DATABASE_URL)
        except psycopg2.OperationalError:
            time.sleep(2)
    return psycopg2.connect(DATABASE_URL)


init_db()


class ReviewData(BaseModel):
    id: str
    code: str
    review_output: str
    run_output: str
    fixed_code: str
    fixed_code_language: str = "python"
    timestamp: str


class RepositoryReviewRequest(BaseModel):
    repository_url: str = Field(..., min_length=10)
    username: str = Field("anonymous", min_length=1)
    mode: str = "Full Repository Review"


@app.get("/reviews/{username}")
def get_reviews(username: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, code, review_output, run_output, fixed_code, fixed_code_language, timestamp
                   FROM reviews WHERE username=%s ORDER BY timestamp DESC""",
                (username,),
            )
            reviews = cur.fetchall()

    tabs = {}
    for review in reviews:
        repository_id = review[0]
        tabs[repository_id] = {
            "code": review[1],
            "review_output": review[2],
            "run_output": review[3],
            "fixed_code": review[4],
            "fixed_code_language": review[5],
            "timestamp": review[6],
            "editor_key": 0,
            "analysis": get_repository_bundle(repository_id, raise_missing=False),
        }
    return tabs


@app.post("/reviews/{username}")
def save_review(username: str, review: ReviewData):
    start = time.perf_counter()
    analysis = analyze_code(review.code or "", filename=review.id)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reviews
                   (id, username, code, review_output, run_output, fixed_code, fixed_code_language, timestamp)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                   username = EXCLUDED.username,
                   code = EXCLUDED.code,
                   review_output = EXCLUDED.review_output,
                   run_output = EXCLUDED.run_output,
                   fixed_code = EXCLUDED.fixed_code,
                   fixed_code_language = EXCLUDED.fixed_code_language,
                   timestamp = EXCLUDED.timestamp""",
                (
                    review.id,
                    username,
                    review.code,
                    review.review_output,
                    review.run_output,
                    review.fixed_code,
                    review.fixed_code_language,
                    review.timestamp,
                ),
            )
            persist_analysis(cur, review.id, analysis)
        conn.commit()
    elapsed = time.perf_counter() - start
    logger.info(
        json.dumps(
            {
                "event": "review_saved",
                "repository_id": review.id,
                "username": username,
                "duration_ms": round(elapsed * 1000, 2),
            }
        )
    )
    return {"message": "Review saved", "analysis": analysis}


@app.delete("/reviews/{tab_id}")
def delete_review(tab_id: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reviews WHERE id=%s", (tab_id,))
        conn.commit()
    return {"message": "Review deleted"}


@app.post("/review/repository", status_code=202)
def start_repository_review(request: RepositoryReviewRequest):
    mode = normalize_review_mode(request.mode)
    try:
        validate_github_url(request.repository_url)
    except RepositoryReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job_id = str(uuid.uuid4())
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO repository_review_jobs
                   (id, username, repository_url, mode, status, progress)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (job_id, request.username, request.repository_url, mode, "queued", 0),
            )
        conn.commit()

    enqueue_repository_review_job(job_id, request.repository_url, mode)
    return {"job_id": job_id, "status": "running", "progress": 5}


@app.get("/review/status/{job_id}")
def get_repository_review_status(job_id: str):
    job = fetch_review_job(job_id)
    if job["status"] == "queued":
        enqueue_repository_review_job(job["id"], job["repository_url"], job["mode"])
        job = fetch_review_job(job_id)
    return {
        "job_id": job["id"],
        "repository_url": job["repository_url"],
        "mode": job["mode"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job["error"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


@app.get("/review/result/{job_id}")
def get_repository_review_result(job_id: str):
    job = fetch_review_job(job_id)
    if job["status"] == "queued":
        enqueue_repository_review_job(job["id"], job["repository_url"], job["mode"])
        job = fetch_review_job(job_id)
    if job["status"] == "failed":
        raise HTTPException(status_code=500, detail=job["error"] or "Repository review failed.")
    if job["status"] != "completed":
        raise HTTPException(status_code=202, detail={"status": job["status"], "progress": job["progress"]})
    return {
        "job_id": job["id"],
        "repository_url": job["repository_url"],
        "mode": job["mode"],
        "status": job["status"],
        "result": job["result"],
    }


@app.get("/api/metrics/{repository_id}")
def get_metrics(repository_id: str):
    return fetch_one(
        """SELECT repository_id, filename, loc, classes, functions, variables, imports,
                  comment_percentage, cyclomatic_complexity, maintainability_score,
                  technical_debt_score, code_quality_score, variable_analysis, function_analysis
           FROM repository_metrics WHERE repository_id=%s""",
        repository_id,
    )


@app.get("/api/memory/{repository_id}")
def get_memory(repository_id: str):
    return fetch_one("SELECT repository_id, score, patterns, recommendations FROM memory_analysis WHERE repository_id=%s", repository_id)


@app.get("/api/performance/{repository_id}")
def get_performance(repository_id: str):
    return fetch_one(
        "SELECT repository_id, score, nested_loops, patterns, recommendations FROM performance_analysis WHERE repository_id=%s",
        repository_id,
    )


@app.get("/api/health/{repository_id}")
def get_health(repository_id: str):
    return fetch_one("SELECT repository_id, score, rating, components FROM health_scores WHERE repository_id=%s", repository_id)


@app.get("/api/recommendations/{repository_id}")
def get_recommendations(repository_id: str):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT category, message, priority, created_at
                   FROM optimization_recommendations
                   WHERE repository_id=%s ORDER BY id ASC""",
                (repository_id,),
            )
            rows = cur.fetchall()
    return {"repository_id": repository_id, "recommendations": normalize_rows(rows)}


@app.get("/api/analysis/{repository_id}")
def get_analysis(repository_id: str):
    return get_repository_bundle(repository_id, raise_missing=True)


def normalize_review_mode(mode: str) -> str:
    cleaned = (mode or "Full Repository Review").strip()
    if cleaned not in REVIEW_MODES:
        raise HTTPException(status_code=400, detail=f"Unsupported review mode. Choose one of: {', '.join(sorted(REVIEW_MODES))}")
    return cleaned


def fetch_review_job(job_id: str):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT id, username, repository_url, mode, status, progress, result, error, created_at, updated_at
                   FROM repository_review_jobs WHERE id=%s""",
                (job_id,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Repository review job not found")
    return normalize_row(row)


def update_review_job(job_id: str, status: str | None = None, progress: int | None = None, result=None, error: str | None = None):
    fields = ["updated_at = CURRENT_TIMESTAMP"]
    values: list[Any] = []
    if status is not None:
        fields.append("status = %s")
        values.append(status)
    if progress is not None:
        fields.append("progress = %s")
        values.append(max(0, min(100, progress)))
    if result is not None:
        fields.append("result = %s")
        values.append(Json(result))
    if error is not None:
        fields.append("error = %s")
        values.append(error)
    values.append(job_id)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE repository_review_jobs SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()


def enqueue_repository_review_job(job_id: str, repository_url: str, mode: str) -> None:
    if job_id in ENQUEUED_REPOSITORY_JOBS:
        return
    ENQUEUED_REPOSITORY_JOBS.add(job_id)
    update_review_job(job_id, status="running", progress=5, error="")
    REPOSITORY_REVIEW_EXECUTOR.submit(process_repository_review_job, job_id, repository_url, mode)


def process_repository_review_job(job_id: str, repository_url: str, mode: str):
    logger.info(json.dumps({"event": "repository_review_started", "job_id": job_id, "repository_url": repository_url, "mode": mode}))
    try:
        update_review_job(job_id, status="running", progress=5)

        def set_progress(progress: int):
            update_review_job(job_id, status="running", progress=progress)

        result = run_repository_review(repository_url, mode, AI_SERVICE_URL, progress_callback=set_progress)
        update_review_job(job_id, status="completed", progress=100, result=result, error="")
        logger.info(json.dumps({"event": "repository_review_finished", "job_id": job_id}))
    except Exception as exc:
        logger.exception(json.dumps({"event": "repository_review_failed", "job_id": job_id}))
        update_review_job(job_id, status="failed", progress=100, error=str(exc))
    finally:
        ENQUEUED_REPOSITORY_JOBS.discard(job_id)


def persist_analysis(cur, repository_id: str, analysis: dict[str, Any]) -> None:
    metrics = analysis["metrics"]
    cur.execute(
        """INSERT INTO repository_metrics
           (repository_id, filename, loc, classes, functions, variables, imports, comment_percentage,
            cyclomatic_complexity, maintainability_score, technical_debt_score, code_quality_score,
            variable_analysis, function_analysis, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (repository_id) DO UPDATE SET
            filename = EXCLUDED.filename,
            loc = EXCLUDED.loc,
            classes = EXCLUDED.classes,
            functions = EXCLUDED.functions,
            variables = EXCLUDED.variables,
            imports = EXCLUDED.imports,
            comment_percentage = EXCLUDED.comment_percentage,
            cyclomatic_complexity = EXCLUDED.cyclomatic_complexity,
            maintainability_score = EXCLUDED.maintainability_score,
            technical_debt_score = EXCLUDED.technical_debt_score,
            code_quality_score = EXCLUDED.code_quality_score,
            variable_analysis = EXCLUDED.variable_analysis,
            function_analysis = EXCLUDED.function_analysis,
            updated_at = CURRENT_TIMESTAMP""",
        (
            repository_id,
            analysis["filename"],
            metrics["loc"],
            metrics["classes"],
            metrics["functions"],
            metrics["variables"],
            metrics["imports"],
            metrics["comment_percentage"],
            metrics["cyclomatic_complexity"],
            metrics["maintainability_score"],
            metrics["technical_debt_score"],
            metrics["code_quality_score"],
            Json(analysis["variables"]),
            Json(analysis["functions"]),
        ),
    )
    cur.execute(
        """INSERT INTO memory_analysis (repository_id, score, patterns, recommendations, updated_at)
           VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (repository_id) DO UPDATE SET
            score = EXCLUDED.score,
            patterns = EXCLUDED.patterns,
            recommendations = EXCLUDED.recommendations,
            updated_at = CURRENT_TIMESTAMP""",
        (
            repository_id,
            analysis["memory"]["score"],
            Json(analysis["memory"]["patterns"]),
            Json(analysis["memory"]["recommendations"]),
        ),
    )
    cur.execute(
        """INSERT INTO performance_analysis (repository_id, score, nested_loops, patterns, recommendations, updated_at)
           VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (repository_id) DO UPDATE SET
            score = EXCLUDED.score,
            nested_loops = EXCLUDED.nested_loops,
            patterns = EXCLUDED.patterns,
            recommendations = EXCLUDED.recommendations,
            updated_at = CURRENT_TIMESTAMP""",
        (
            repository_id,
            analysis["performance"]["score"],
            analysis["performance"]["nested_loops"],
            Json(analysis["performance"]["patterns"]),
            Json(analysis["performance"]["recommendations"]),
        ),
    )
    cur.execute(
        """INSERT INTO health_scores (repository_id, score, rating, components, updated_at)
           VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (repository_id) DO UPDATE SET
            score = EXCLUDED.score,
            rating = EXCLUDED.rating,
            components = EXCLUDED.components,
            updated_at = CURRENT_TIMESTAMP""",
        (
            repository_id,
            analysis["health"]["score"],
            analysis["health"]["rating"],
            Json(analysis["health"]["components"]),
        ),
    )
    cur.execute("DELETE FROM optimization_recommendations WHERE repository_id=%s", (repository_id,))
    for rec in analysis["recommendations"]:
        cur.execute(
            """INSERT INTO optimization_recommendations (repository_id, category, message, priority)
               VALUES (%s, %s, %s, %s)""",
            (repository_id, rec["category"], rec["message"], rec["priority"]),
        )


def fetch_one(query: str, repository_id: str):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (repository_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Repository analysis not found")
    return normalize_row(row)


def get_repository_bundle(repository_id: str, raise_missing: bool = False):
    try:
        metrics = get_metrics(repository_id)
        memory = get_memory(repository_id)
        performance = get_performance(repository_id)
        health = get_health(repository_id)
        recommendations = get_recommendations(repository_id)["recommendations"]
        return {
            "metrics": metrics,
            "memory": memory,
            "performance": performance,
            "health": health,
            "recommendations": recommendations,
        }
    except HTTPException:
        if raise_missing:
            raise
        return None


def normalize_rows(rows):
    return [normalize_row(row) for row in rows]


def normalize_row(row):
    normalized = dict(row)
    for key, value in list(normalized.items()):
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        elif hasattr(value, "__float__"):
            try:
                normalized[key] = float(value)
            except (TypeError, ValueError):
                pass
    return normalized
