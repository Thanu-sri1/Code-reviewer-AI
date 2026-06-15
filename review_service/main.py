import json
import logging
import os
import time
from datetime import datetime
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException, Response
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel

from analyzers import analyze_code


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"review-service","message":"%(message)s"}',
)
logger = logging.getLogger("review-service")

app = FastAPI(title="Review Management Service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://coderaptor:coderaptor@postgres:5432/coderaptor")
REQUEST_COUNT = 0
REQUEST_LATENCY_SECONDS = 0.0


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
                    timestamp TEXT)"""
            )
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
    timestamp: str


@app.get("/reviews/{username}")
def get_reviews(username: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, code, review_output, run_output, fixed_code, timestamp
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
            "timestamp": review[5],
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
                   (id, username, code, review_output, run_output, fixed_code, timestamp)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET
                   username = EXCLUDED.username,
                   code = EXCLUDED.code,
                   review_output = EXCLUDED.review_output,
                   run_output = EXCLUDED.run_output,
                   fixed_code = EXCLUDED.fixed_code,
                   timestamp = EXCLUDED.timestamp""",
                (
                    review.id,
                    username,
                    review.code,
                    review.review_output,
                    review.run_output,
                    review.fixed_code,
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
