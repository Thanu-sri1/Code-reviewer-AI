import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from analyzers import analyze_code


IGNORE_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "target",
    ".terraform",
}
SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".java", ".yaml", ".yml", ".json"}
SPECIAL_FILENAMES = {"Dockerfile", "Jenkinsfile", "azure-pipelines.yml", ".gitlab-ci.yml"}
PIPELINE_PATTERNS = (
    ".github/workflows/",
    "azure-pipelines.yml",
    "Jenkinsfile",
    ".gitlab-ci.yml",
)
MAX_FILE_BYTES = int(os.getenv("REPOSITORY_REVIEW_MAX_FILE_BYTES", "200000"))
MAX_FILES = int(os.getenv("REPOSITORY_REVIEW_MAX_FILES", "250"))
MAX_AI_FILE_CHARS = int(os.getenv("REPOSITORY_REVIEW_MAX_AI_FILE_CHARS", "12000"))
MAX_AI_TOTAL_CHARS = int(os.getenv("REPOSITORY_REVIEW_MAX_AI_TOTAL_CHARS", "90000"))


class RepositoryReviewError(Exception):
    pass


def validate_github_url(repository_url: str) -> str:
    repository_url = (repository_url or "").strip()
    match = re.match(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$", repository_url)
    if not match:
        raise RepositoryReviewError("Only HTTPS GitHub repository URLs like https://github.com/user/project are supported.")
    owner, repo = match.groups()
    return f"https://github.com/{owner}/{repo}.git"


def clone_repository(repository_url: str, destination: Path) -> None:
    clone_url = validate_github_url(repository_url)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", clone_url, str(destination)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError as exc:
        raise RepositoryReviewError("Git is not installed in the review-service container.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RepositoryReviewError("Repository clone timed out.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Git clone failed.").strip()
        raise RepositoryReviewError(detail[-500:]) from exc


def scan_repository(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    ignored = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if should_ignore_path(path, root):
            ignored += 1
            continue
        if not is_supported_file(path):
            continue
        if is_binary_file(path) or path.stat().st_size > MAX_FILE_BYTES:
            ignored += 1
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            ignored += 1
            continue
        files.append(build_file_record(relative, content))
        if len(files) >= MAX_FILES:
            break

    return {
        "files": files,
        "ignored_files": ignored,
        "summary": build_repository_summary(root, files),
        "pipeline_files": [item for item in files if item["is_pipeline"]],
        "local_analysis": aggregate_local_analysis(files),
    }


def should_ignore_path(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(part in IGNORE_DIRS for part in relative_parts)


def is_supported_file(path: Path) -> bool:
    name = path.name
    relative = path.as_posix()
    return name in SPECIAL_FILENAMES or path.suffix.lower() in SUPPORTED_EXTENSIONS or ".github/workflows/" in relative


def is_binary_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\0" in sample


def build_file_record(relative_path: str, content: str) -> dict[str, Any]:
    suffix = Path(relative_path).suffix.lower()
    language = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".java": "Java",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".json": "JSON",
    }.get(suffix, "DevOps" if relative_path.endswith(("Dockerfile", "Jenkinsfile")) else "Text")
    return {
        "path": relative_path,
        "language": language,
        "size": len(content.encode("utf-8")),
        "line_count": len(content.splitlines()),
        "is_pipeline": is_pipeline_file(relative_path),
        "content": content,
    }


def is_pipeline_file(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(pattern in normalized for pattern in PIPELINE_PATTERNS)


def build_repository_summary(root: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    languages = Counter(item["language"] for item in files)
    dependency_files = find_dependency_files(root)
    frameworks = detect_frameworks(files, dependency_files)
    return {
        "project_overview": {
            "reviewed_files": len(files),
            "reviewed_lines": sum(item["line_count"] for item in files),
            "pipeline_files": sum(1 for item in files if item["is_pipeline"]),
        },
        "languages_used": dict(languages),
        "frameworks_detected": frameworks,
        "architecture_summary": infer_architecture(files),
        "folder_structure_analysis": folder_structure(files),
        "dependency_analysis": dependency_files,
        "risk_assessment": build_risk_assessment(files, dependency_files),
        "technical_debt_summary": build_technical_debt_summary(files),
    }


def find_dependency_files(root: Path) -> list[dict[str, Any]]:
    names = {
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "pom.xml",
        "build.gradle",
        "Dockerfile",
        "docker-compose.yml",
        "kustomization.yaml",
        "Chart.yaml",
    }
    results = []
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink() and path.name in names and not should_ignore_path(path, root):
            results.append({"path": path.relative_to(root).as_posix(), "type": path.name})
    return results[:50]


def detect_frameworks(files: list[dict[str, Any]], dependency_files: list[dict[str, Any]]) -> list[str]:
    haystack = "\n".join(item["content"][:4000] for item in files[:80]).lower()
    names = {item["type"].lower() for item in dependency_files}
    frameworks = []
    checks = {
        "FastAPI": "fastapi" in haystack,
        "Streamlit": "streamlit" in haystack,
        "React/Node": "package.json" in names or "react" in haystack,
        "Spring/Java": "pom.xml" in names or "build.gradle" in names,
        "Docker": "dockerfile" in names or "docker-compose.yml" in names,
        "Kubernetes": "apiversion:" in haystack and "kind:" in haystack,
        "Terraform": ".terraform" in haystack or "terraform" in haystack,
    }
    for name, detected in checks.items():
        if detected:
            frameworks.append(name)
    return frameworks


def infer_architecture(files: list[dict[str, Any]]) -> str:
    folders = {item["path"].split("/", 1)[0] for item in files if "/" in item["path"]}
    if any(folder.endswith("_service") or folder.endswith("-service") for folder in folders):
        return "Service-oriented repository with independently named service folders."
    if {"src", "tests"}.issubset(folders):
        return "Application repository with source and test separation."
    if any(item["is_pipeline"] for item in files):
        return "Application repository with DevOps pipeline configuration."
    return "General-purpose repository; no strong architecture pattern detected from folder names."


def folder_structure(files: list[dict[str, Any]]) -> dict[str, Any]:
    folders = Counter(item["path"].split("/", 1)[0] if "/" in item["path"] else "." for item in files)
    return {"top_level_folders": dict(folders.most_common(20))}


def build_risk_assessment(files: list[dict[str, Any]], dependency_files: list[dict[str, Any]]) -> list[str]:
    risks = []
    if not any(item["is_pipeline"] for item in files):
        risks.append("No supported CI/CD pipeline file was found.")
    if not any("test" in item["path"].lower() for item in files):
        risks.append("No test folder or test file was detected in reviewed files.")
    if dependency_files and not any("lock" in item["path"].lower() for item in dependency_files):
        risks.append("Dependency manifests were found, but lock files were not detected in the reviewed dependency set.")
    secret_pattern = re.compile(r"(password|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s]{8,}", re.I)
    if any(secret_pattern.search(item["content"]) for item in files):
        risks.append("Possible hardcoded credential patterns were found.")
    return risks or ["No high-level repository risks detected by static metadata scan."]


def build_technical_debt_summary(files: list[dict[str, Any]]) -> list[str]:
    debt = []
    large_files = [item["path"] for item in files if item["line_count"] > 500]
    if large_files:
        debt.append(f"Large files may need splitting: {', '.join(large_files[:5])}")
    if sum(item["line_count"] for item in files) > 20000:
        debt.append("Repository is large enough to need modular review ownership and incremental quality gates.")
    return debt or ["No obvious repository-level technical debt detected from file sizes."]


def aggregate_local_analysis(files: list[dict[str, Any]]) -> dict[str, Any]:
    python_files = [item for item in files if item["path"].endswith(".py")]
    analyses = [analyze_code(item["content"], filename=item["path"]) for item in python_files[:60]]
    if not analyses:
        return {"python_files_analyzed": 0}
    return {
        "python_files_analyzed": len(analyses),
        "loc": sum(item["metrics"]["loc"] for item in analyses),
        "average_maintainability_score": round(
            sum(item["metrics"]["maintainability_score"] for item in analyses) / len(analyses), 2
        ),
        "average_code_quality_score": round(sum(item["metrics"]["code_quality_score"] for item in analyses) / len(analyses), 2),
        "recommendations": [rec for item in analyses for rec in item["recommendations"]][:20],
    }


def build_ai_payload(scan: dict[str, Any], repository_url: str, mode: str) -> dict[str, Any]:
    selected = []
    budget = MAX_AI_TOTAL_CHARS
    prioritized = sorted(scan["files"], key=lambda item: (not item["is_pipeline"], item["path"]))
    for item in prioritized:
        content = item["content"][:MAX_AI_FILE_CHARS]
        if len(content) > budget:
            continue
        selected.append({key: item[key] for key in ("path", "language", "line_count", "is_pipeline")} | {"content": content})
        budget -= len(content)
        if budget <= 0:
            break
    return {
        "repository_url": repository_url,
        "mode": mode,
        "summary": scan["summary"],
        "local_analysis": scan["local_analysis"],
        "files": selected,
    }


def call_ai_repository_review(ai_service_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{ai_service_url.rstrip('/')}/review/repository",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RepositoryReviewError(f"AI service failed: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RepositoryReviewError(f"Unable to connect to AI service: {exc.reason}") from exc


def run_repository_review(repository_url: str, mode: str, ai_service_url: str, progress_callback=None) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix="repo-review-"))
    repo_path = temp_root / "repo"
    try:
        if progress_callback:
            progress_callback(15)
        clone_repository(repository_url, repo_path)
        if progress_callback:
            progress_callback(40)
        scan = scan_repository(repo_path)
        if progress_callback:
            progress_callback(65)
        ai_payload = build_ai_payload(scan, repository_url, mode)
        ai_result = call_ai_repository_review(ai_service_url, ai_payload)
        if progress_callback:
            progress_callback(90)
        return {
            "repository_url": repository_url,
            "mode": mode,
            "summary": scan["summary"],
            "pipeline_files": [{"path": item["path"], "line_count": item["line_count"]} for item in scan["pipeline_files"]],
            "local_analysis": scan["local_analysis"],
            "ai_report": ai_result.get("report", ""),
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
