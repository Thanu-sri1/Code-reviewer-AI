# pyrefly: ignore [missing-import]
from fastapi import FastAPI
from fastapi import Response
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Optional

import yaml


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"execution-service","message":"%(message)s"}',
)
logger = logging.getLogger("execution-service")

app = FastAPI(title="Execution Service")
REQUEST_COUNT = 0
REQUEST_LATENCY_SECONDS = 0.0
EXECUTION_TIMEOUT_SECONDS = int(os.getenv("EXECUTION_TIMEOUT_SECONDS", "30"))


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
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
            }
        )
    )
    return response


@app.get("/health")
def health_check():
    return {"service": "execution-service", "status": "ok"}


@app.get("/ready")
def readiness_check():
    return {
        "service": "execution-service",
        "status": "ready",
        "runtimes": available_runtimes(),
    }


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
    language: str = "python"


class CodeResponse(BaseModel):
    output: str


@app.post("/run", response_model=CodeResponse)
def run_code(request: CodeRequest):
    """Execute or validate code for the requested language."""
    language = normalize_language(request.language)
    safe_tab_id = safe_filename_part(request.tab_id)
    work_dir = Path(f"run_{safe_tab_id}")
    work_dir.mkdir(exist_ok=True)

    try:
        if language == "python":
            output = run_python(request.code, work_dir)
        elif language == "java":
            output = run_java(request.code, work_dir)
        elif language == "javascript":
            output = run_javascript(request.code, work_dir)
        elif language == "yaml":
            output = validate_yaml(request.code)
        else:
            output = (
                f"Execution is not configured for {language.upper()} yet. "
                "Supported languages: Python, Java, JavaScript, YAML validation."
            )
        return {"output": output}
    except subprocess.TimeoutExpired:
        return {"output": f"Error: Code execution timed out ({EXECUTION_TIMEOUT_SECONDS} second limit)"}
    except Exception as exc:
        return {"output": f"Error: {str(exc)}"}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def normalize_language(language: str) -> str:
    language = (language or "python").strip().lower()
    aliases = {
        "py": "python",
        "yml": "yaml",
        "js": "javascript",
        "node": "javascript",
    }
    return aliases.get(language, language)


def safe_filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value or "code")[:80]


def available_runtimes():
    return {
        "python": bool(shutil.which("python3")),
        "java": bool(shutil.which("javac") and shutil.which("java")),
        "javascript": bool(shutil.which("node")),
        "yaml": True,
    }


def run_python(code: str, work_dir: Path) -> str:
    source = work_dir / "main.py"
    source.write_text(code)
    result = subprocess.run(
        ["python3", str(source)],
        capture_output=True,
        text=True,
        timeout=EXECUTION_TIMEOUT_SECONDS,
    )
    return format_process_output(result)


def run_java(code: str, work_dir: Path) -> str:
    if not shutil.which("javac") or not shutil.which("java"):
        return "Java runtime is not installed in the execution service container."

    class_name = find_java_class_name(code)
    source = work_dir / f"{class_name}.java"
    source.write_text(code)

    compile_result = subprocess.run(
        ["javac", str(source.name)],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=EXECUTION_TIMEOUT_SECONDS,
    )
    if compile_result.returncode != 0:
        return "Compilation failed:\n" + (compile_result.stderr or compile_result.stdout)

    run_result = subprocess.run(
        ["java", class_name],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=EXECUTION_TIMEOUT_SECONDS,
    )
    return format_process_output(run_result)


def find_java_class_name(code: str) -> str:
    public_match = re.search(r"public\s+class\s+([A-Za-z_][A-Za-z0-9_]*)", code)
    if public_match:
        return public_match.group(1)
    class_match = re.search(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", code)
    if class_match:
        return class_match.group(1)
    return "Main"


def run_javascript(code: str, work_dir: Path) -> str:
    if not shutil.which("node"):
        return "Node.js runtime is not installed in the execution service container."

    source = work_dir / "main.js"
    source.write_text(code)
    result = subprocess.run(
        ["node", str(source)],
        capture_output=True,
        text=True,
        timeout=EXECUTION_TIMEOUT_SECONDS,
    )
    return format_process_output(result)


def validate_yaml(code: str) -> str:
    parsed = yaml.safe_load(code)
    kind = type(parsed).__name__
    normalized_yaml = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True).strip()

    if isinstance(parsed, dict):
        structure_errors = validate_kubernetes_structure(parsed)
        if structure_errors:
            return "\n".join(
                [
                    "Error: YAML syntax is valid, but the Kubernetes structure is incorrect.",
                    *[f"- {error}" for error in structure_errors],
                    "",
                    "Parsed YAML:",
                    normalized_yaml,
                ]
            )

        top_level = ", ".join(str(key) for key in list(parsed.keys())[:8])
        summary = [
            "YAML is valid.",
            f"Top-level keys: {top_level or 'none'}.",
        ]
        if isinstance(parsed.get("metadata"), dict) and parsed["metadata"].get("name"):
            summary.append(f"Resource name: {parsed['metadata']['name']}.")
        if parsed.get("kind"):
            summary.append(f"Kind: {parsed['kind']}.")
        summary.extend(["", "Validated YAML:", normalized_yaml])
        return "\n".join(summary)
    if isinstance(parsed, list):
        return f"YAML is valid. It contains a list with {len(parsed)} item(s).\n\nValidated YAML:\n{normalized_yaml}"
    return f"YAML is valid. Parsed value type: {kind}.\n\nValidated YAML:\n{normalized_yaml}"


def validate_kubernetes_structure(parsed: dict) -> list[str]:
    if "apiVersion" not in parsed and "kind" not in parsed:
        return []

    errors = []
    if not parsed.get("apiVersion"):
        errors.append("Missing or empty `apiVersion`.")
    if not parsed.get("kind"):
        errors.append("Missing or empty `kind`.")

    metadata = parsed.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("`metadata` must contain nested fields. Example: metadata -> name.")
    elif not metadata.get("name"):
        errors.append("`metadata.name` is required.")

    if parsed.get("kind") == "Pod":
        validate_pod_spec(parsed.get("spec"), "spec", errors)

    if parsed.get("kind") == "Deployment":
        spec = parsed.get("spec")
        if not isinstance(spec, dict):
            errors.append("`spec` must contain nested Deployment settings.")
        else:
            replicas = spec.get("replicas")
            if replicas is not None and (not isinstance(replicas, int) or replicas < 0):
                errors.append("`spec.replicas` must be a non-negative integer.")

            selector_labels = spec.get("selector", {}).get("matchLabels") if isinstance(spec.get("selector"), dict) else None
            template = spec.get("template")
            template_labels = template.get("metadata", {}).get("labels") if isinstance(template, dict) and isinstance(template.get("metadata"), dict) else None
            if not isinstance(selector_labels, dict) or not selector_labels:
                errors.append("`spec.selector.matchLabels` must be provided.")
            if not isinstance(template_labels, dict) or not template_labels:
                errors.append("`spec.template.metadata.labels` must be provided.")
            if isinstance(selector_labels, dict) and isinstance(template_labels, dict):
                for key, value in selector_labels.items():
                    if template_labels.get(key) != value:
                        errors.append(
                            f"`spec.selector.matchLabels.{key}` must match `spec.template.metadata.labels.{key}`."
                        )

            template_spec = template.get("spec") if isinstance(template, dict) else None
            validate_pod_spec(template_spec, "spec.template.spec", errors)

    misplaced_keys = []
    for key in ("name", "containers"):
        if key in parsed:
            misplaced_keys.append(key)
    if misplaced_keys:
        errors.append(
            "These fields look misplaced at the top level: "
            + ", ".join(f"`{key}`" for key in misplaced_keys)
            + ". Check indentation."
        )

    return errors


def validate_pod_spec(spec, path: str, errors: list[str]) -> None:
    if not isinstance(spec, dict):
        errors.append(f"`{path}` must contain nested Pod settings.")
        return

    containers = spec.get("containers")
    if not isinstance(containers, list) or not containers:
        errors.append(f"`{path}.containers` must be a non-empty list.")
        return

    for index, container in enumerate(containers):
        container_path = f"{path}.containers[{index}]"
        if not isinstance(container, dict):
            errors.append(f"`{container_path}` must be an object.")
            continue
        if not container.get("name"):
            errors.append(f"`{container_path}.name` is required.")
        if not container.get("image"):
            errors.append(f"`{container_path}.image` is required.")
        validate_container_ports(container.get("ports"), container_path, errors)
        validate_env(container.get("env"), container_path, errors)
        validate_resources(container.get("resources"), container_path, errors)


def validate_container_ports(ports, container_path: str, errors: list[str]) -> None:
    if ports is None:
        return
    if not isinstance(ports, list):
        errors.append(f"`{container_path}.ports` must be a list.")
        return
    for index, port in enumerate(ports):
        port_path = f"{container_path}.ports[{index}].containerPort"
        if not isinstance(port, dict):
            errors.append(f"`{container_path}.ports[{index}]` must be an object.")
            continue
        container_port = port.get("containerPort")
        if not isinstance(container_port, int) or not 1 <= container_port <= 65535:
            errors.append(f"`{port_path}` must be an integer between 1 and 65535.")


def validate_env(env, container_path: str, errors: list[str]) -> None:
    if env is None:
        return
    if not isinstance(env, list):
        errors.append(f"`{container_path}.env` must be a list.")
        return
    for index, item in enumerate(env):
        env_path = f"{container_path}.env[{index}]"
        if not isinstance(item, dict):
            errors.append(f"`{env_path}` must be an object.")
            continue
        if not item.get("name"):
            errors.append(f"`{env_path}.name` is required.")
        if "value" in item and item.get("value") is None:
            errors.append(f"`{env_path}.value` must not be null. Use an empty string or valueFrom.")


def validate_resources(resources, container_path: str, errors: list[str]) -> None:
    if resources is None:
        return
    if not isinstance(resources, dict):
        errors.append(f"`{container_path}.resources` must be an object.")
        return

    requests = resources.get("requests", {})
    limits = resources.get("limits", {})
    if requests is not None and not isinstance(requests, dict):
        errors.append(f"`{container_path}.resources.requests` must be an object.")
        return
    if limits is not None and not isinstance(limits, dict):
        errors.append(f"`{container_path}.resources.limits` must be an object.")
        return

    request_memory = parse_memory_quantity((requests or {}).get("memory"))
    limit_memory = parse_memory_quantity((limits or {}).get("memory"))
    if request_memory is not None and limit_memory is not None and request_memory > limit_memory:
        errors.append(f"`{container_path}.resources.requests.memory` must be less than or equal to limits.memory.")


def parse_memory_quantity(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None

    match = re.fullmatch(r"(\d+(?:\.\d+)?)(Ki|Mi|Gi|Ti|K|M|G|T)?", value.strip())
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2) or ""
    multipliers = {
        "": 1,
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    return int(amount * multipliers[unit])


def format_process_output(result: subprocess.CompletedProcess) -> str:
    output = result.stdout or ""
    if result.stderr:
        output += ("\nErrors:\n" if output else "Errors:\n") + result.stderr
    if not output.strip() and result.returncode == 0:
        output = "Program completed successfully, but it did not print any output."
    return output
