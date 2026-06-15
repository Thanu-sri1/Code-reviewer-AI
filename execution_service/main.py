# pyrefly: ignore [missing-import]
from fastapi import FastAPI
from fastapi import Response
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
import json
import logging
import subprocess
import os
import time

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"execution-service","message":"%(message)s"}',
)
logger = logging.getLogger("execution-service")

app = FastAPI(title="Execution Service")
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
    logger.info(json.dumps({"event": "request_completed", "path": request.url.path, "status_code": response.status_code, "duration_ms": round(elapsed * 1000, 2)}))
    return response

@app.get("/health")
def health_check():
    return {"service": "execution-service", "status": "ok"}

@app.get("/ready")
def readiness_check():
    return {"service": "execution-service", "status": "ready"}

@app.get("/live")
def liveness_check():
    return {"service": "execution-service", "status": "alive"}

@app.get("/metrics")
def prometheus_metrics():
    return Response(
        content=f"execution_service_requests_total {REQUEST_COUNT}\nexecution_service_request_latency_seconds_total {REQUEST_LATENCY_SECONDS:.6f}\n",
        media_type="text/plain; version=0.0.4",
    )

class CodeRequest(BaseModel):
    code: str
    tab_id: str

class CodeResponse(BaseModel):
    output: str

@app.post("/run", response_model=CodeResponse)
def run_code(request: CodeRequest):
    """Execute Python code and capture output."""
    temp_file = f"temp_{request.tab_id}.py"
    try:
        # Create a temporary file to execute the code
        with open(temp_file, "w") as f:
            f.write(request.code)
        
        # Run the code and capture output
        result = subprocess.run(
            ["python3", temp_file],
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        # Return both stdout and stderr
        output = result.stdout
        if result.stderr:
            output += "\nErrors:\n" + result.stderr
        if not output.strip() and result.returncode == 0:
            output = "Program completed successfully, but it did not print any output."
            
        return {"output": output}
    except subprocess.TimeoutExpired:
        return {"output": "Error: Code execution timed out (30 second limit)"}
    except Exception as e:
        return {"output": f"Error: {str(e)}"}
    finally:
        # Ensure temp file is removed even if there's an error
        if os.path.exists(temp_file):
            os.remove(temp_file)
