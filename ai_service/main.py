import ast
import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"ai-service","message":"%(message)s"}',
)
logger = logging.getLogger("ai-service")

app = FastAPI(title="AI Service")
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


def read_env_value(name: str) -> str:
    value = (os.getenv(name) or "").strip().strip("\"'")
    if value:
        return value

    file_path = os.getenv(f"{name}_FILE") or f"/mnt/secrets-store/{name}"
    if Path(file_path).exists():
        return Path(file_path).read_text().strip().strip("\"'")

    for env_path in (Path.cwd() / ".env", Path.cwd().parent / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            env_name, env_value = line.split("=", 1)
            if env_name.strip() == name:
                return env_value.strip().strip("\"'")

    return ""


AZURE_OPENAI_ENDPOINT = read_env_value("AZURE_OPENAI_ENDPOINT").rstrip("/")
AZURE_OPENAI_API_KEY = read_env_value("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT = read_env_value("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = read_env_value("AZURE_OPENAI_API_VERSION") or "2025-01-01-preview"


SYSTEM_PROMPT = """You are a helpful code reviewer. Your task is to:
- Explain problems in simple words that students and beginners can understand.
- Find bugs, risky code, slow code, unused variables, and confusing functions.
- Suggest simple improvements for memory use, speed, readability, and structure.
- Provide corrected code only when a clear fix is needed.

Response format:
1. Problems Found
   - Explain each issue in simple language.
   - Say why it matters.

2. Simple Suggestions
   - Give short, practical suggestions.
   - Use beginner-friendly terms.
   - Avoid unnecessary theory.

3. Corrected Code
   - First identify the input language.
   - Provide one compact corrected version in the same language as the user's input.
   - If the input is YAML, return YAML in a yaml code block.
   - If the input is Java, return Java in a java code block.
   - If the input is Python, return Python in a python code block.
   - Preserve the user's original purpose and style as much as possible.
   - Fix only what is needed.
   - Do not rewrite the code into a large framework, class hierarchy, CLI app, or production template.
   - If the original code is already runnable, return the same code with only minimal improvements.
   - Explain changes outside the code block.

Important:
- Do not convert YAML, Java, JavaScript, C++, or any other language into Python unless the user explicitly asks for conversion.
- Put the final corrected code in exactly one section titled "Corrected Code".
- Wrap only the corrected code in one fenced code block with the correct language identifier.
"""

EXTRACT_PROMPT = """Extract only the programming code from this image.
Do not include explanations, comments, markdown, JSON, headers, or extra text.
Preserve indentation, special characters, and syntax exactly as seen in the image.
If the image does not contain code, return: No code detected in the image.
"""


class ReviewRequest(BaseModel):
    code: str
    mode: str = "Full Repository Review"


class RepositoryFile(BaseModel):
    path: str
    language: str
    line_count: int = 0
    is_pipeline: bool = False
    content: str


class RepositoryReviewRequest(BaseModel):
    repository_url: str
    mode: str = "Full Repository Review"
    summary: dict[str, Any] = Field(default_factory=dict)
    local_analysis: dict[str, Any] = Field(default_factory=dict)
    files: list[RepositoryFile] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    review_output: str
    fixed_code: str
    fixed_code_language: str = "text"


class RepositoryReviewResponse(BaseModel):
    report: str


class AzureAIError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@app.get("/health")
def health_check():
    return {
        "service": "ai-service",
        "status": "ok",
        "provider": "azure-openai",
        "endpoint_loaded": bool(AZURE_OPENAI_ENDPOINT),
        "key_loaded": bool(AZURE_OPENAI_API_KEY),
        "deployment_loaded": bool(AZURE_OPENAI_DEPLOYMENT),
    }


@app.get("/ready")
def readiness_check():
    missing = missing_azure_config()
    if missing:
        raise HTTPException(status_code=503, detail=f"Azure OpenAI config missing: {', '.join(missing)}")
    return {"service": "ai-service", "status": "ready", "provider": "azure-openai"}


@app.get("/live")
def liveness_check():
    return {"service": "ai-service", "status": "alive"}


@app.get("/metrics")
def prometheus_metrics():
    payload = "\n".join(
        [
            "# HELP ai_service_requests_total Total HTTP requests handled by AI service.",
            "# TYPE ai_service_requests_total counter",
            f"ai_service_requests_total {REQUEST_COUNT}",
            "# HELP ai_service_request_latency_seconds_total Cumulative request latency.",
            "# TYPE ai_service_request_latency_seconds_total counter",
            f"ai_service_request_latency_seconds_total {REQUEST_LATENCY_SECONDS:.6f}",
            "",
        ]
    )
    return Response(content=payload, media_type="text/plain; version=0.0.4")


def missing_azure_config() -> list[str]:
    missing = []
    if not AZURE_OPENAI_ENDPOINT:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not AZURE_OPENAI_API_KEY:
        missing.append("AZURE_OPENAI_API_KEY")
    if not AZURE_OPENAI_DEPLOYMENT:
        missing.append("AZURE_OPENAI_DEPLOYMENT")
    if not AZURE_OPENAI_API_VERSION:
        missing.append("AZURE_OPENAI_API_VERSION")
    return missing


def azure_chat_completion(messages: list[dict], max_tokens: int = 1800, temperature: float = 0.2) -> str:
    missing = missing_azure_config()
    if missing:
        raise AzureAIError(500, f"Azure OpenAI config missing: {', '.join(missing)}")

    url = (
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}"
        f"/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"
    )
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "api-key": AZURE_OPENAI_API_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AzureAIError(exc.code, parse_azure_error(detail))
    except urllib.error.URLError as exc:
        raise AzureAIError(503, f"Unable to connect to Azure OpenAI: {exc.reason}")

    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise AzureAIError(502, "Azure OpenAI returned an unexpected response.")


def parse_azure_error(detail: str) -> str:
    try:
        payload = json.loads(detail)
        error = payload.get("error", {})
        message = error.get("message") or detail
        code = error.get("code")
        return f"{code}: {message}" if code else message
    except json.JSONDecodeError:
        return detail or "Azure OpenAI request failed."


def extract_corrected_code_block(text: str) -> tuple[str, str]:
    blocks = []
    for match in re.finditer(r"```([A-Za-z0-9_+.-]*)\s*\n(.*?)```", text, re.DOTALL):
        language = normalize_language(match.group(1))
        code = match.group(2).strip()
        if code:
            blocks.append((language, code, match.start()))

    if not blocks:
        return "", "text"

    corrected_index = text.lower().rfind("corrected code")
    preferred_blocks = [block for block in blocks if corrected_index == -1 or block[2] > corrected_index]
    for language, code, _ in reversed(preferred_blocks or blocks):
        if language == "python" and not is_valid_runnable_python(code):
            continue
        return code, language
    return "", "text"


def normalize_language(language: str) -> str:
    language = (language or "text").strip().lower()
    aliases = {
        "yml": "yaml",
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "c++": "cpp",
        "c#": "csharp",
    }
    return aliases.get(language, language or "text")


def is_valid_runnable_python(code: str) -> bool:
    if not code.strip():
        return False
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True


def friendly_ai_error(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, AzureAIError):
        status_code = exc.status_code
        message = exc.message
    else:
        status_code = 500
        message = str(exc)

    lowered = message.lower()
    if status_code == 401 or "unauthorized" in lowered or "access denied" in lowered:
        return 401, "Azure OpenAI authentication failed. Check AZURE_OPENAI_API_KEY."
    if status_code == 404 or "deployment" in lowered and "not found" in lowered:
        return 404, "Azure OpenAI deployment was not found. Check AZURE_OPENAI_DEPLOYMENT and region."
    if status_code == 429 or "quota" in lowered or "rate" in lowered:
        return 429, "Azure OpenAI quota or rate limit reached. Retry later or increase quota in Azure."
    return status_code, message


@app.post("/review", response_model=ReviewResponse)
def review_code(request: ReviewRequest):
    started = time.perf_counter()
    try:
        focus = repository_mode_focus(request.mode)
        prompt = f"""Review this code in simple words and provide a minimal fix.

Review mode: {request.mode}
Mode focus: {focus}

Include these sections:
- Problems Found
- Simple Suggestions
- Corrected Code

For the corrected code:
- Detect the input language and return corrected code in that same language.
- For YAML, use a ```yaml code block.
- For Java, use a ```java code block.
- For Python, use a ```python code block.
- Keep the same behavior as the user's code.
- Do not add unnecessary classes, services, menus, config files, comments, frameworks, or advanced patterns.
- Do not convert YAML, Java, JavaScript, C++, or other languages into Python.
- Put the final corrected code in exactly one fenced code block under "Corrected Code".

Code:
{request.code}
"""
        review_output = azure_chat_completion(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        fixed_code, fixed_code_language = extract_corrected_code_block(review_output)

        elapsed = time.perf_counter() - started
        logger.info(
            json.dumps(
                {
                    "event": "review_completed",
                    "provider": "azure-openai",
                    "deployment": AZURE_OPENAI_DEPLOYMENT,
                    "duration_ms": round(elapsed * 1000, 2),
                    "input_chars": len(request.code),
                    "fixed_code_chars": len(fixed_code),
                    "fixed_code_language": fixed_code_language,
                }
            )
        )
        return {
            "review_output": review_output,
            "fixed_code": fixed_code,
            "fixed_code_language": fixed_code_language,
        }
    except Exception as exc:
        logger.exception(
            json.dumps({"event": "review_failed", "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
        )
        status_code, detail = friendly_ai_error(exc)
        raise HTTPException(status_code=status_code, detail=detail)


def repository_mode_focus(mode: str) -> str:
    normalized = (mode or "").strip().lower()
    mapping = {
        "security review": "Prioritize exploitable vulnerabilities, secret handling, authentication, authorization, dependency risk, and CI/CD supply-chain security.",
        "performance review": "Prioritize slow code paths, inefficient algorithms, excessive I/O, build time, caching, concurrency, and scalability risks.",
        "best practices review": "Prioritize maintainability, readability, error handling, testing, dependency hygiene, architecture boundaries, and framework conventions.",
        "devops review": "Prioritize pipeline safety, approvals, environment separation, artifact management, caching, rollback, tests, quality gates, and vulnerability scanning.",
        "full repository review": "Review security, performance, best practices, DevOps, maintainability, architecture, dependencies, and technical debt.",
    }
    return mapping.get(normalized, mapping["full repository review"])


def format_repository_files(files: list[RepositoryFile]) -> str:
    sections = []
    for file_item in files:
        sections.append(
            "\n".join(
                [
                    f"### File: {file_item.path}",
                    f"Language: {file_item.language}",
                    f"Lines: {file_item.line_count}",
                    f"Pipeline file: {file_item.is_pipeline}",
                    "```",
                    file_item.content,
                    "```",
                ]
            )
        )
    return "\n\n".join(sections)


@app.post("/review/repository", response_model=RepositoryReviewResponse)
def review_repository(request: RepositoryReviewRequest):
    started = time.perf_counter()
    try:
        focus = repository_mode_focus(request.mode)
        prompt = f"""Review this GitHub repository using the selected mode.

Repository URL: {request.repository_url}
Review mode: {request.mode}
Mode focus: {focus}

Repository metadata:
{json.dumps(request.summary, indent=2)}

Local static analysis:
{json.dumps(request.local_analysis, indent=2)}

Files selected for review:
{format_repository_files(request.files)}

Return a production-ready Markdown report with exactly these top-level sections:

1. Project Overview
2. Languages Used
3. Frameworks Detected
4. Architecture Summary
5. Folder Structure Analysis
6. Dependency Analysis
7. Code Quality Report
8. Security Findings
9. Performance Issues
10. Best Practice Violations
11. Pipeline Review Report
12. Risk Assessment
13. Technical Debt Summary
14. Maintainability Score
15. Prioritized Action Plan

Pipeline Review Report must explicitly evaluate GitHub Actions, Azure DevOps, Jenkins, and GitLab files when present. Identify hardcoded secrets, missing approvals, missing environment separation, inefficient stages, missing artifact management, missing caching, missing rollback strategy, missing test stages, missing code quality gates, and missing vulnerability scanning.

Use severity labels Critical, High, Medium, Low. Include file paths for findings. If evidence is insufficient, say so and recommend what to inspect next. Do not invent files or line numbers that were not provided.
"""
        report = azure_chat_completion(
            [
                {"role": "system", "content": "You are a senior software architect, security reviewer, and DevOps reviewer."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.2,
        )
        logger.info(
            json.dumps(
                {
                    "event": "repository_review_completed",
                    "provider": "azure-openai",
                    "deployment": AZURE_OPENAI_DEPLOYMENT,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "file_count": len(request.files),
                    "mode": request.mode,
                }
            )
        )
        return {"report": report}
    except Exception as exc:
        logger.exception(json.dumps({"event": "repository_review_failed"}))
        status_code, detail = friendly_ai_error(exc)
        raise HTTPException(status_code=status_code, detail=detail)


@app.post("/extract")
async def extract_code(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        content_type = file.content_type or "image/png"
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{content_type};base64,{encoded_image}"
        extracted_code = azure_chat_completion(
            [
                {"role": "system", "content": EXTRACT_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACT_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            max_tokens=1200,
            temperature=0,
        )
        return {"extracted_code": extracted_code.strip()}
    except Exception as exc:
        status_code, detail = friendly_ai_error(exc)
        raise HTTPException(status_code=status_code, detail=detail)
