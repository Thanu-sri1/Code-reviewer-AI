from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
import hashlib
import json
import logging
import os
import time
import psycopg2
from psycopg2 import errors

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"auth-service","message":"%(message)s"}',
)
logger = logging.getLogger("auth-service")

app = FastAPI(title="Auth Service")
REQUEST_COUNT = 0
REQUEST_LATENCY_SECONDS = 0.0

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://coderaptor:coderaptor@postgres:5432/coderaptor")

@app.middleware("http")
async def track_requests(request, call_next):
    global REQUEST_COUNT, REQUEST_LATENCY_SECONDS
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    REQUEST_COUNT += 1
    REQUEST_LATENCY_SECONDS += elapsed
    logger.info(json.dumps({"event": "request_completed", "path": request.url.path, "status_code": response.status_code, "duration_ms": round(elapsed * 1000, 2)}))
    return response

@app.get("/health")
def health_check():
    return {"service": "auth-service", "status": "ok"}

@app.get("/ready")
def readiness_check():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"service": "auth-service", "status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

@app.get("/live")
def liveness_check():
    return {"service": "auth-service", "status": "alive"}

@app.get("/metrics")
def prometheus_metrics():
    return Response(
        content=f"auth_service_requests_total {REQUEST_COUNT}\nauth_service_request_latency_seconds_total {REQUEST_LATENCY_SECONDS:.6f}\n",
        media_type="text/plain; version=0.0.4",
    )

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS users
                           (username TEXT PRIMARY KEY,
                            email TEXT UNIQUE NOT NULL,
                            password TEXT NOT NULL)''')
        conn.commit()

def get_db_connection():
    for _ in range(10):
        try:
            return psycopg2.connect(DATABASE_URL)
        except psycopg2.OperationalError:
            time.sleep(2)
    return psycopg2.connect(DATABASE_URL)

# Initialize DB on startup
init_db()

def hash_password(password: str) -> str:
    salt = "anthropic_secure_salt"
    return hashlib.sha256((password + salt).encode()).hexdigest()

class UserAuth(BaseModel):
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str

@app.post("/register")
def register_user(user: UserRegister):
    if not user.username or not user.email or not user.password:
        raise HTTPException(status_code=400, detail="Username, email, and password required")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO users (username, email, password) VALUES (%s, %s, %s)',
                    (user.username, str(user.email), hash_password(user.password)),
                )
            conn.commit()
        return {"message": "Registration successful"}
    except errors.UniqueViolation:
        raise HTTPException(status_code=400, detail="Username or email already exists")

@app.post("/login")
def login(user: UserAuth):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT username, password FROM users WHERE email=%s', (str(user.email),))
            result = cur.fetchone()
    
    if result and result[1] == hash_password(user.password):
        # In a full production system, return a JWT token here
        # For simplicity, returning a success flag
        return {"message": "Login successful", "username": result[0], "email": str(user.email)}
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
