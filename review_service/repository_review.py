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
MAX_UI_FILE_CHARS = int(os.getenv("REPOSITORY_REVIEW_MAX_UI_FILE_CHARS", "30000"))


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
    prompt_injection_findings = scan_prompt_injection_risks(files)
    risk_heatmap = build_risk_heatmap(files)
    production_readiness = calculate_production_readiness(files, dependency_files, risk_heatmap)
    sprint_plan = build_sprint_fix_plan(files, dependency_files, risk_heatmap, production_readiness)
    release_gate = build_release_gate(production_readiness, risk_heatmap, prompt_injection_findings)
    threat_model = build_threat_model(files, frameworks, prompt_injection_findings)
    onboarding_guide = build_onboarding_guide(files, frameworks, dependency_files, production_readiness, release_gate)
    release_readiness = build_release_readiness_platform(
        files,
        dependency_files,
        risk_heatmap,
        production_readiness,
        release_gate,
    )
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
        "production_readiness_score": production_readiness,
        "risk_heatmap": risk_heatmap,
        "architecture_diagram": build_architecture_diagram(files, frameworks),
        "sprint_fix_plan": sprint_plan,
        "release_gate": release_gate,
        "threat_model": threat_model,
        "prompt_injection_scan": prompt_injection_findings,
        "onboarding_guide": onboarding_guide,
        "release_readiness": release_readiness,
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


def build_risk_heatmap(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    heatmap = []
    secret_pattern = re.compile(r"(password|secret|token|api[_-]?key|connectionstring)\s*[:=]\s*['\"]?[^'\"\s]{8,}", re.I)
    risky_code_pattern = re.compile(r"\b(eval|exec|pickle\.loads|os\.system|subprocess\.Popen|shell=True)\b")
    for item in files:
        score = 0
        reasons = []
        path = item["path"].lower()
        content = item["content"]
        if secret_pattern.search(content):
            score += 35
            reasons.append("possible hardcoded secret")
        if risky_code_pattern.search(content):
            score += 20
            reasons.append("risky runtime execution pattern")
        if item["is_pipeline"]:
            missing = pipeline_missing_controls(content)
            if missing:
                score += min(30, len(missing) * 6)
                reasons.append(f"pipeline controls missing: {', '.join(missing[:4])}")
        if path.endswith((".yaml", ".yml")) and "kind: deployment" in content.lower():
            if "readinessprobe" not in content.lower():
                score += 10
                reasons.append("missing Kubernetes readiness probe")
            if "resources:" not in content.lower():
                score += 10
                reasons.append("missing Kubernetes resource limits/requests")
        if item["line_count"] > 500:
            score += 12
            reasons.append("large file")
        if "test" not in path and item["language"] in {"Python", "JavaScript", "TypeScript", "Java"}:
            score += 5
            reasons.append("source file may need matching tests")
        if score:
            heatmap.append(
                {
                    "path": item["path"],
                    "score": min(score, 100),
                    "severity": severity_from_score(score),
                    "reasons": reasons,
                }
            )
    return sorted(heatmap, key=lambda row: row["score"], reverse=True)[:25]


def pipeline_missing_controls(content: str) -> list[str]:
    lowered = content.lower()
    checks = {
        "test stage": ("test" in lowered or "pytest" in lowered or "npm test" in lowered or "mvn test" in lowered),
        "quality gate": ("sonar" in lowered or "lint" in lowered or "quality" in lowered),
        "vulnerability scan": ("trivy" in lowered or "snyk" in lowered or "grype" in lowered or "dependency-check" in lowered),
        "artifact management": ("artifact" in lowered or "upload-artifact" in lowered or "publish" in lowered),
        "cache": ("cache" in lowered or "actions/cache" in lowered),
        "rollback": ("rollback" in lowered),
        "approval/environment gate": ("environment:" in lowered or "approval" in lowered or "manualvalidation" in lowered),
    }
    return [name for name, present in checks.items() if not present]


def severity_from_score(score: int) -> str:
    if score >= 70:
        return "Critical"
    if score >= 45:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def calculate_production_readiness(
    files: list[dict[str, Any]],
    dependency_files: list[dict[str, Any]],
    risk_heatmap: list[dict[str, Any]],
) -> dict[str, Any]:
    has_tests = any("test" in item["path"].lower() for item in files)
    has_pipeline = any(item["is_pipeline"] for item in files)
    has_k8s = any("apiversion:" in item["content"].lower() and "kind:" in item["content"].lower() for item in files)
    has_docker = any(item["path"].endswith("Dockerfile") or item["path"].endswith("docker-compose.yml") for item in files)
    has_dependency_manifest = bool(dependency_files)
    has_lock_file = any("lock" in item["path"].lower() for item in dependency_files)
    critical_or_high = sum(1 for item in risk_heatmap if item["severity"] in {"Critical", "High"})
    pipeline_files = [item for item in files if item["is_pipeline"]]
    missing_pipeline_controls = sorted({control for item in pipeline_files for control in pipeline_missing_controls(item["content"])})

    components = {
        "security": max(0, 100 - critical_or_high * 15 - sum(1 for item in risk_heatmap if item["severity"] == "Medium") * 5),
        "testing": 80 if has_tests else 35,
        "devops": max(20, 85 - len(missing_pipeline_controls) * 8) if has_pipeline else 25,
        "maintainability": max(30, 90 - sum(1 for item in files if item["line_count"] > 500) * 10),
        "deployment": 85 if has_k8s and has_docker else 60 if has_docker or has_k8s else 35,
        "dependency_hygiene": 80 if has_dependency_manifest and has_lock_file else 55 if has_dependency_manifest else 35,
    }
    overall = round(sum(components.values()) / len(components), 2)
    if overall >= 85:
        rating = "Production Ready"
    elif overall >= 70:
        rating = "Mostly Ready"
    elif overall >= 50:
        rating = "Needs Hardening"
    else:
        rating = "Not Production Ready"
    return {
        "overall": overall,
        "rating": rating,
        "components": components,
        "missing_pipeline_controls": missing_pipeline_controls,
    }


def build_architecture_diagram(files: list[dict[str, Any]], frameworks: list[str]) -> dict[str, Any]:
    folders = sorted({item["path"].split("/", 1)[0] for item in files if "/" in item["path"]})
    service_folders = [folder for folder in folders if folder.endswith("_service") or folder.endswith("-service")]
    nodes = service_folders or folders[:8]
    lines = ["flowchart LR"]
    if not nodes:
        lines.append('    repo["Repository"]')
    else:
        for node in nodes:
            label = node.replace("_", " ").replace("-", " ").title()
            lines.append(f'    {mermaid_id(node)}["{label}"]')
        if "frontend" in nodes:
            for node in nodes:
                if node != "frontend":
                    lines.append(f"    frontend --> {mermaid_id(node)}")
        if "review_service" in nodes and "ai_service" in nodes:
            lines.append("    review_service --> ai_service")
    if any("Azure" in name for name in frameworks) or any("openai" in item["content"].lower() for item in files):
        lines.append('    ai_service --> azure_openai["Azure OpenAI"]')
    if any("DATABASE_URL" in item["content"] or "postgres" in item["content"].lower() for item in files):
        lines.append('    auth_service --> postgres["PostgreSQL"]')
        lines.append('    review_service --> postgres')
    return {
        "format": "mermaid",
        "diagram": "\n".join(dict.fromkeys(lines)),
        "detected_nodes": nodes,
    }


def mermaid_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def build_sprint_fix_plan(
    files: list[dict[str, Any]],
    dependency_files: list[dict[str, Any]],
    risk_heatmap: list[dict[str, Any]],
    production_readiness: dict[str, Any],
) -> list[dict[str, Any]]:
    critical_high = [item for item in risk_heatmap if item["severity"] in {"Critical", "High"}]
    medium = [item for item in risk_heatmap if item["severity"] == "Medium"]
    has_tests = any("test" in item["path"].lower() for item in files)
    has_pipeline = any(item["is_pipeline"] for item in files)
    sprints = [
        {
            "name": "Sprint 1 - Blocker Hardening",
            "goal": "Remove release blockers and obvious security exposure.",
            "tasks": [f"Fix {item['severity']} risk in {item['path']}: {', '.join(item['reasons'][:2])}" for item in critical_high[:5]],
        },
        {
            "name": "Sprint 2 - Quality Gates",
            "goal": "Make every change measurable before merge.",
            "tasks": [],
        },
        {
            "name": "Sprint 3 - Production Operations",
            "goal": "Improve deployability, rollback confidence, and maintainability.",
            "tasks": [f"Reduce medium risk in {item['path']}: {', '.join(item['reasons'][:2])}" for item in medium[:5]],
        },
    ]
    if not has_tests:
        sprints[1]["tasks"].append("Add unit/integration tests for the main source folders and repository review workflow.")
    if not has_pipeline:
        sprints[1]["tasks"].append("Add a CI pipeline with tests, linting, artifact publishing, and vulnerability scanning.")
    for control in production_readiness.get("missing_pipeline_controls", [])[:6]:
        sprints[1]["tasks"].append(f"Add CI/CD control: {control}.")
    if dependency_files and not any("lock" in item["path"].lower() for item in dependency_files):
        sprints[2]["tasks"].append("Commit dependency lock files or document deterministic dependency resolution.")
    if production_readiness["overall"] < 70:
        sprints[2]["tasks"].append("Raise production readiness score above 70 by addressing weakest score components.")
    for sprint in sprints:
        if not sprint["tasks"]:
            sprint["tasks"].append("No urgent task detected for this sprint from static repository intelligence.")
    return sprints


def build_release_gate(
    production_readiness: dict[str, Any],
    risk_heatmap: list[dict[str, Any]],
    prompt_injection_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers = []
    warnings = []
    critical = [item for item in risk_heatmap if item["severity"] == "Critical"]
    high = [item for item in risk_heatmap if item["severity"] == "High"]
    readiness = production_readiness.get("overall", 0)
    if critical:
        blockers.extend([f"Critical repository risk in {item['path']}" for item in critical[:5]])
    if len(high) >= 3:
        blockers.append(f"{len(high)} high-severity repository risks require remediation before release.")
    if readiness < 50:
        blockers.append(f"Production readiness is {readiness}, below the release threshold of 50.")
    if prompt_injection_findings:
        blockers.append("Repository contains text that may attempt prompt injection against AI review workflows.")
    for control in production_readiness.get("missing_pipeline_controls", [])[:5]:
        warnings.append(f"Missing pipeline control: {control}.")
    if readiness < 70 and readiness >= 50:
        warnings.append(f"Production readiness is {readiness}; release should be conditional on hardening tasks.")

    if blockers:
        decision = "BLOCKED"
    elif warnings:
        decision = "APPROVED_WITH_WARNINGS"
    else:
        decision = "APPROVED"
    return {
        "decision": decision,
        "readiness_threshold": 70,
        "blockers": blockers,
        "warnings": warnings,
        "next_action": release_next_action(decision),
    }


def release_next_action(decision: str) -> str:
    if decision == "BLOCKED":
        return "Resolve blockers, rerun repository review, and require approval before deployment."
    if decision == "APPROVED_WITH_WARNINGS":
        return "Create follow-up issues for warnings and proceed only with owner sign-off."
    return "Proceed with normal release checks."


def scan_prompt_injection_risks(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    patterns = {
        "instruction_override": re.compile(r"ignore (all )?(previous|above|prior) instructions", re.I),
        "secret_exfiltration": re.compile(r"(reveal|print|dump|send).{0,40}(secret|api key|token|environment variable|system prompt)", re.I),
        "role_manipulation": re.compile(r"(you are now|act as|developer mode|jailbreak)", re.I),
        "tool_abuse": re.compile(r"(run|execute).{0,30}(curl|wget|powershell|bash|cmd|rm -rf)", re.I),
    }
    findings = []
    for item in files:
        matches = []
        for name, pattern in patterns.items():
            if pattern.search(item["content"]):
                matches.append(name)
        if matches:
            findings.append(
                {
                    "path": item["path"],
                    "severity": "High" if "secret_exfiltration" in matches or "instruction_override" in matches else "Medium",
                    "patterns": matches,
                    "recommendation": "Treat this file as untrusted prompt content; quote it, delimit it, and instruct the model not to follow repository instructions.",
                }
            )
    return findings[:20]


def build_threat_model(
    files: list[dict[str, Any]],
    frameworks: list[str],
    prompt_injection_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    has_frontend = any(item["path"].startswith("frontend/") for item in files)
    has_api = any("fastapi" in item["content"].lower() or item["path"].endswith("_service/main.py") for item in files)
    has_k8s = any("apiversion:" in item["content"].lower() and "kind:" in item["content"].lower() for item in files)
    has_pipeline = any(item["is_pipeline"] for item in files)
    assets = ["source code", "review reports", "repository URLs", "AI prompts and responses"]
    if any("DATABASE_URL" in item["content"] or "postgres" in item["content"].lower() for item in files):
        assets.append("application database")
    if any("AZURE_OPENAI" in item["content"] for item in files):
        assets.append("Azure OpenAI credentials")
    entry_points = []
    if has_frontend:
        entry_points.append("browser frontend")
    if has_api:
        entry_points.append("FastAPI service endpoints")
    if has_pipeline:
        entry_points.append("CI/CD pipeline triggers")
    entry_points.append("GitHub repository URL input")
    trust_boundaries = [
        "user browser to frontend",
        "frontend to internal services",
        "review service to cloned repository content",
        "review service to Azure OpenAI",
    ]
    if has_k8s:
        trust_boundaries.append("cluster ingress to Kubernetes services")

    stride = [
        {"category": "Spoofing", "risk": "Unauthenticated or weakly authenticated users may impersonate reviewers.", "mitigation": "Require authentication and signed tokens on review actions."},
        {"category": "Tampering", "risk": "Repository content can manipulate review inputs or pipeline definitions.", "mitigation": "Treat cloned files as untrusted, scan prompt injection, and never execute repository code."},
        {"category": "Repudiation", "risk": "Review decisions may lack audit trail.", "mitigation": "Persist job owner, repository URL, mode, timestamp, and release decision."},
        {"category": "Information Disclosure", "risk": "Secrets may be sent to AI if committed in source.", "mitigation": "Redact detected secrets before AI calls and fail release gates on credential findings."},
        {"category": "Denial of Service", "risk": "Large repositories can exhaust clone, scan, or token budgets.", "mitigation": "Keep file count, file size, timeout, and token limits enforced."},
        {"category": "Elevation of Privilege", "risk": "Pipeline misconfiguration can deploy unreviewed changes.", "mitigation": "Require environment approvals, quality gates, and vulnerability scans."},
    ]
    if prompt_injection_findings:
        stride.append(
            {
                "category": "AI Prompt Injection",
                "risk": f"{len(prompt_injection_findings)} files contain possible model-instruction attacks.",
                "mitigation": "Delimit repository content, ignore instructions inside files, and review flagged files manually.",
            }
        )
    return {
        "assets": assets,
        "entry_points": entry_points,
        "trust_boundaries": trust_boundaries,
        "framework_context": frameworks,
        "stride": stride,
    }


def build_onboarding_guide(
    files: list[dict[str, Any]],
    frameworks: list[str],
    dependency_files: list[dict[str, Any]],
    production_readiness: dict[str, Any],
    release_gate: dict[str, Any],
) -> dict[str, Any]:
    top_folders = folder_structure(files)["top_level_folders"]
    important_files = []
    for candidate in ("README.md", "docker-compose.yml", "requirements.txt", "package.json", "Dockerfile", "azure-pipelines.yml", "Jenkinsfile"):
        important_files.extend(item["path"] for item in files if item["path"].endswith(candidate))
    important_files.extend(item["path"] for item in files if item["is_pipeline"])
    first_tasks = [
        f"Review release decision: {release_gate['decision']}.",
        "Read the architecture diagram and identify service boundaries.",
        "Run the test suite or add tests if no tests are detected.",
        "Inspect the risk heatmap before making changes.",
    ]
    if production_readiness.get("overall", 0) < 70:
        first_tasks.append("Prioritize the sprint fix plan before feature work.")
    return {
        "repo_type": infer_architecture(files),
        "frameworks_to_learn": frameworks or ["No framework confidently detected"],
        "important_folders": top_folders,
        "important_files": sorted(set(important_files))[:20],
        "local_setup_hints": build_local_setup_hints(dependency_files),
        "first_day_tasks": first_tasks,
        "questions_new_developer_should_ask": [
            "Which findings are release blockers?",
            "Which service owns authentication and authorization?",
            "Where are secrets stored and rotated?",
            "What tests must pass before merge?",
            "How are deployments rolled back?",
        ],
    }


def build_local_setup_hints(dependency_files: list[dict[str, Any]]) -> list[str]:
    names = {item["type"] for item in dependency_files}
    hints = []
    if "docker-compose.yml" in names:
        hints.append("Use docker compose up --build for local multi-service startup.")
    if "requirements.txt" in names:
        hints.append("Install Python dependencies from requirements.txt in the relevant service folder.")
    if "package.json" in names:
        hints.append("Run npm install before frontend or Node-based scripts.")
    if "pom.xml" in names:
        hints.append("Use Maven commands such as mvn test for Java modules.")
    return hints or ["No setup manifest detected; start with README or top-level service folders."]


def build_release_readiness_platform(
    files: list[dict[str, Any]],
    dependency_files: list[dict[str, Any]],
    risk_heatmap: list[dict[str, Any]],
    production_readiness: dict[str, Any],
    release_gate: dict[str, Any],
) -> dict[str, Any]:
    deployment_prediction = predict_deployment_failures(files)
    cost_detection = detect_cost_leakage(files)
    production_impact = predict_production_impact(files, risk_heatmap)
    component_scores = calculate_release_component_scores(
        files,
        dependency_files,
        risk_heatmap,
        production_readiness,
        deployment_prediction,
        cost_detection,
        production_impact,
    )
    overall = round(sum(component_scores.values()) / len(component_scores), 2)
    blockers = release_gate.get("blockers", [])[:5] + [
        issue["issue"] for issue in deployment_prediction["issues"] if issue["risk_level"] in {"Critical", "High"}
    ][:5]
    fix_now = build_fix_now_actions(deployment_prediction, cost_detection, production_impact, risk_heatmap)
    return {
        "release_readiness_score": overall,
        "decision": release_decision_from_score(overall, blockers),
        "scores": component_scores,
        "blockers": blockers[:8],
        "fix_now": fix_now[:8],
        "predictions": {
            "production_failure_risk": deployment_prediction["production_failure_risk"],
            "deployment_failure_probability": deployment_prediction["deployment_failure_probability"],
            "performance_bottlenecks": production_impact["performance_bottlenecks"],
            "cloud_cost_waste": cost_detection["cloud_cost_waste"],
        },
        "dashboard_cards": [
            {"label": "Release Readiness", "value": overall, "unit": "/100", "status": release_decision_from_score(overall, blockers)},
            {"label": "Deployment Failure", "value": deployment_prediction["deployment_failure_probability"], "unit": "%", "status": deployment_prediction["production_failure_risk"]},
            {"label": "Monthly Cost Waste", "value": cost_detection["estimated_monthly_savings_inr"], "unit": "INR", "status": cost_detection["cloud_cost_waste"]},
            {"label": "Critical Fixes", "value": len(blockers[:8]), "unit": "", "status": "Action Required" if blockers else "Clear"},
        ],
    }


def calculate_release_component_scores(
    files: list[dict[str, Any]],
    dependency_files: list[dict[str, Any]],
    risk_heatmap: list[dict[str, Any]],
    production_readiness: dict[str, Any],
    deployment_prediction: dict[str, Any],
    cost_detection: dict[str, Any],
    production_impact: dict[str, Any],
) -> dict[str, float]:
    readiness_components = production_readiness.get("components", {})
    security = readiness_components.get("security", 70)
    maintainability = readiness_components.get("maintainability", 70)
    deployment = max(0, 100 - deployment_prediction["deployment_failure_probability"])
    cost = max(0, 100 - min(80, cost_detection["estimated_monthly_savings_inr"] / 250))
    performance_penalty = len(production_impact["performance_bottlenecks"]) * 12
    performance = max(0, 85 - performance_penalty)
    if not any("test" in item["path"].lower() for item in files):
        maintainability = max(0, maintainability - 15)
    if dependency_files and not any("lock" in item["path"].lower() for item in dependency_files):
        security = max(0, security - 8)
    if any(item["severity"] == "Critical" for item in risk_heatmap):
        security = max(0, security - 20)
    return {
        "security": round(security, 2),
        "performance": round(performance, 2),
        "deployment": round(deployment, 2),
        "cost_optimization": round(cost, 2),
        "maintainability": round(maintainability, 2),
    }


def predict_deployment_failures(files: list[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    dockerfiles = [item for item in files if item["path"].endswith("Dockerfile")]
    k8s_files = [item for item in files if item["path"].endswith((".yaml", ".yml")) and "kind:" in item["content"].lower()]
    pipeline_files = [item for item in files if item["is_pipeline"]]
    for item in dockerfiles:
        content = item["content"].lower()
        if "expose" not in content and "port" not in content:
            issues.append(release_issue(item["path"], "Missing container port declaration", "Service may start but fail traffic routing in App Service or Kubernetes.", "High", "Add EXPOSE and align app port with service targetPort.", "EXPOSE 8000"))
        if "user " not in content:
            issues.append(release_issue(item["path"], "Container runs as root", "AKS restricted policies or security reviews may block deployment.", "High", "Create and switch to a non-root user.", "RUN adduser --disabled-password appuser\nUSER appuser"))
        if "healthcheck" not in content:
            issues.append(release_issue(item["path"], "Missing Docker healthcheck", "Orchestrators have weaker signals for failed containers.", "Medium", "Add a HEALTHCHECK that calls the service health endpoint.", "HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1"))
    for item in k8s_files:
        lower = item["content"].lower()
        if "kind: deployment" not in lower:
            continue
        if "readinessprobe" not in lower:
            issues.append(release_issue(item["path"], "Readiness probe missing", "Rolling updates may send traffic to pods before the app is ready.", "High", "Add readinessProbe to every container.", "readinessProbe:\n  httpGet:\n    path: /ready\n    port: 8000\n  initialDelaySeconds: 10\n  periodSeconds: 10"))
        if "livenessprobe" not in lower:
            issues.append(release_issue(item["path"], "Liveness probe missing", "Hung containers may stay alive and serve failures.", "Medium", "Add livenessProbe to restart unhealthy pods.", "livenessProbe:\n  httpGet:\n    path: /live\n    port: 8000\n  initialDelaySeconds: 30\n  periodSeconds: 20"))
        if "resources:" not in lower:
            issues.append(release_issue(item["path"], "Resource requests and limits missing", "Pods can be evicted or overconsume node resources.", "High", "Add CPU and memory requests/limits.", "resources:\n  requests:\n    cpu: 250m\n    memory: 512Mi\n  limits:\n    cpu: 500m\n    memory: 1Gi"))
        if "imagepullpolicy: always" in lower and ":latest" in lower:
            issues.append(release_issue(item["path"], "Mutable latest image tag", "Rollbacks and reproducible deploys become unreliable.", "High", "Pin immutable version tags or digests.", "image: youracr.azurecr.io/app:v1.2.3"))
    for item in pipeline_files:
        missing = pipeline_missing_controls(item["content"])
        if "rollback" in missing:
            issues.append(
                release_issue(
                    item["path"],
                    "Rollback stage missing",
                    "Failed production deployments may require manual recovery.",
                    "High",
                    "Add a rollback step that runs when deployment verification fails.",
                    rollback_fix_snippet(item["path"]),
                )
            )
        if "artifact management" in missing:
            issues.append(
                release_issue(
                    item["path"],
                    "Artifact publishing missing",
                    "Deployments may not have traceable build outputs.",
                    "Medium",
                    "Publish build outputs or scan reports as pipeline artifacts.",
                    artifact_fix_snippet(item["path"]),
                )
            )
    probability = min(95, 15 + sum({"Critical": 28, "High": 18, "Medium": 10, "Low": 4}[item["risk_level"]] for item in issues))
    return {
        "deployment_failure_probability": probability,
        "production_failure_risk": risk_band(probability),
        "issues": issues[:20],
    }


def detect_cost_leakage(files: list[dict[str, Any]]) -> dict[str, Any]:
    findings = []
    total_current = 0
    total_recommended = 0
    for item in files:
        if not item["path"].endswith((".yaml", ".yml")):
            continue
        resources = extract_k8s_resource_requests(item["content"])
        for resource in resources:
            current = estimate_monthly_inr(resource["cpu_m"], resource["memory_mi"])
            recommended_cpu = min(resource["cpu_m"], 500) if resource["cpu_m"] > 0 else 250
            recommended_memory = min(resource["memory_mi"], 1024) if resource["memory_mi"] > 0 else 512
            recommended = estimate_monthly_inr(recommended_cpu, recommended_memory)
            total_current += current
            total_recommended += recommended
            if current - recommended >= 1500:
                findings.append(
                    {
                        "file": item["path"],
                        "issue": "Potential oversized Kubernetes resource request",
                        "impact": "Over-requested CPU/memory can reserve expensive AKS capacity and increase monthly cloud cost.",
                        "risk_level": "High" if current - recommended >= 8000 else "Medium",
                        "current_monthly_cost_inr": current,
                        "recommended_monthly_cost_inr": recommended,
                        "estimated_savings_inr": current - recommended,
                        "exact_fix": "Right-size requests and keep limits close to observed runtime usage.",
                        "fixed_code": f"resources:\n  requests:\n    cpu: {recommended_cpu}m\n    memory: {format_memory(recommended_memory)}\n  limits:\n    cpu: {recommended_cpu * 2}m\n    memory: {format_memory(recommended_memory * 2)}",
                    }
                )
    savings = max(0, total_current - total_recommended)
    return {
        "cloud_cost_waste": "High" if savings >= 10000 else "Medium" if savings >= 3000 else "Low",
        "estimated_monthly_cost_inr": total_current,
        "recommended_monthly_cost_inr": total_recommended,
        "estimated_monthly_savings_inr": savings,
        "findings": findings[:20],
    }


def predict_production_impact(files: list[dict[str, Any]], risk_heatmap: list[dict[str, Any]]) -> dict[str, Any]:
    bottlenecks = []
    for item in files:
        content = item["content"]
        lower = content.lower()
        if re.search(r"for .+:\s*\n(?:.|\n){0,300}(requests\.|cursor\.execute|\.execute\(|fetchone|fetchall)", content):
            bottlenecks.append(impact_issue(item["path"], "I/O or database call inside loop", "Response Time: 2.1s", "Response Time: 8.7s after 100k users", "High", "Batch requests or prefetch data outside the loop.", "Expected response time near 1.2s and cloud cost reduction up to 35%."))
        if "fetchall(" in lower:
            bottlenecks.append(impact_issue(item["path"], "Unbounded fetchall usage", "Memory: moderate on small data", "Memory spike or worker crash on large tables", "High", "Use pagination, streaming cursors, or bounded queries.", "Lower peak memory and fewer pod restarts."))
        if item["line_count"] > 700:
            bottlenecks.append(impact_issue(item["path"], "Very large file", "Change risk: medium", "Higher regression risk during release", "Medium", "Split responsibilities into smaller modules.", "Faster review and lower defect probability."))
    if any(row["severity"] in {"Critical", "High"} for row in risk_heatmap):
        bottlenecks.append(impact_issue("repository", "High-risk files present", "Release confidence: reduced", "Production incident probability increases", "High", "Resolve high-risk heatmap findings before release.", "Improved release confidence and lower support burden."))
    return {
        "performance_bottlenecks": bottlenecks[:20],
        "highest_risk": "High" if any(item["risk_level"] == "High" for item in bottlenecks) else "Medium" if bottlenecks else "Low",
    }


def release_issue(file_path: str, issue: str, impact: str, risk_level: str, exact_fix: str, fixed_code: str) -> dict[str, str]:
    return {
        "file": file_path,
        "issue": issue,
        "impact": impact,
        "risk_level": risk_level,
        "exact_fix": exact_fix,
        "fixed_code": fixed_code,
    }


def rollback_fix_snippet(file_path: str) -> str:
    path = file_path.lower()
    if ".github/workflows/" in path:
        return """- name: Verify AKS rollout
  run: |
    kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s

- name: Rollback AKS deployment
  if: failure()
  run: |
    kubectl rollout undo deployment/<deployment-name> -n <namespace>
    kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s
"""
    if "azure-pipelines" in path:
        return """- script: |
    kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s
  displayName: Verify AKS rollout

- script: |
    kubectl rollout undo deployment/<deployment-name> -n <namespace>
    kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s
  displayName: Rollback AKS deployment
  condition: failed()
"""
    if "jenkinsfile" in path:
        return """stage('Verify Rollout') {
  steps {
    sh 'kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s'
  }
}

post {
  failure {
    sh 'kubectl rollout undo deployment/<deployment-name> -n <namespace>'
    sh 'kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s'
  }
}
"""
    if ".gitlab-ci" in path:
        return """verify_rollout:
  stage: deploy
  script:
    - kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s

rollback:
  stage: deploy
  when: on_failure
  script:
    - kubectl rollout undo deployment/<deployment-name> -n <namespace>
    - kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s
"""
    return """kubectl rollout status deployment/<deployment-name> -n <namespace> --timeout=120s
kubectl rollout undo deployment/<deployment-name> -n <namespace>
"""


def artifact_fix_snippet(file_path: str) -> str:
    path = file_path.lower()
    if ".github/workflows/" in path:
        return """- name: Upload build artifact
  uses: actions/upload-artifact@v4
  with:
    name: build-output
    path: |
      dist/
      reports/
"""
    if "azure-pipelines" in path:
        return """- publish: $(Build.ArtifactStagingDirectory)
  artifact: build-output
  displayName: Publish build artifact
"""
    if "jenkinsfile" in path:
        return """post {
  always {
    archiveArtifacts artifacts: 'dist/**, reports/**', fingerprint: true
  }
}
"""
    if ".gitlab-ci" in path:
        return """artifacts:
  paths:
    - dist/
    - reports/
  expire_in: 7 days
"""
    return """# Publish build outputs and scan reports as CI/CD artifacts.
"""


def impact_issue(file_path: str, issue: str, current: str, projected: str, risk_level: str, exact_fix: str, expected: str) -> dict[str, str]:
    return {
        "file": file_path,
        "issue": issue,
        "current": current,
        "projected_at_scale": projected,
        "risk_level": risk_level,
        "exact_fix": exact_fix,
        "expected_improvement": expected,
    }


def build_fix_now_actions(
    deployment_prediction: dict[str, Any],
    cost_detection: dict[str, Any],
    production_impact: dict[str, Any],
    risk_heatmap: list[dict[str, Any]],
) -> list[dict[str, str]]:
    actions = []
    actions.extend(deployment_prediction["issues"][:4])
    actions.extend(cost_detection["findings"][:2])
    for item in production_impact["performance_bottlenecks"][:2]:
        actions.append(
            {
                "file": item["file"],
                "issue": item["issue"],
                "impact": item["projected_at_scale"],
                "risk_level": item["risk_level"],
                "exact_fix": item["exact_fix"],
                "fixed_code": item["expected_improvement"],
            }
        )
    for item in risk_heatmap[:2]:
        actions.append(
            {
                "file": item["path"],
                "issue": "High repository risk" if item["severity"] in {"Critical", "High"} else "Repository risk",
                "impact": ", ".join(item["reasons"][:2]),
                "risk_level": item["severity"],
                "exact_fix": "Open this file first and remediate the listed risk before release.",
                "fixed_code": "See file-specific recommendation in the risk heatmap.",
            }
        )
    return actions


def extract_k8s_resource_requests(content: str) -> list[dict[str, int]]:
    resources = []
    cpu_matches = re.findall(r"cpu:\s*['\"]?([0-9.]+m?)['\"]?", content, re.I)
    memory_matches = re.findall(r"memory:\s*['\"]?([0-9.]+(?:Mi|Gi|M|G)?)['\"]?", content, re.I)
    for index, cpu in enumerate(cpu_matches):
        memory = memory_matches[index] if index < len(memory_matches) else "0"
        resources.append({"cpu_m": parse_cpu_m(cpu), "memory_mi": parse_memory_mi(memory)})
    return resources


def parse_cpu_m(value: str) -> int:
    value = value.strip()
    if value.endswith("m"):
        return int(float(value[:-1]))
    return int(float(value) * 1000)


def parse_memory_mi(value: str) -> int:
    value = value.strip()
    if value.lower().endswith("gi") or value.lower().endswith("g"):
        return int(float(re.sub(r"[A-Za-z]+$", "", value)) * 1024)
    if value.lower().endswith("mi") or value.lower().endswith("m"):
        return int(float(re.sub(r"[A-Za-z]+$", "", value)))
    return int(float(value)) if value else 0


def estimate_monthly_inr(cpu_m: int, memory_mi: int) -> int:
    cpu_cost = (cpu_m / 1000) * 2400
    memory_cost = (memory_mi / 1024) * 850
    return round(cpu_cost + memory_cost)


def format_memory(memory_mi: int) -> str:
    if memory_mi >= 1024 and memory_mi % 1024 == 0:
        return f"{memory_mi // 1024}Gi"
    return f"{memory_mi}Mi"


def risk_band(probability: int) -> str:
    if probability >= 75:
        return "High"
    if probability >= 45:
        return "Medium"
    return "Low"


def release_decision_from_score(score: float, blockers: list[str]) -> str:
    if blockers or score < 55:
        return "BLOCKED"
    if score < 75:
        return "APPROVED_WITH_WARNINGS"
    return "APPROVED"


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
        "repository_intelligence": extract_repository_intelligence(scan["summary"]),
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
        ai_error = ""
        try:
            ai_result = call_ai_repository_review(ai_service_url, ai_payload)
        except RepositoryReviewError as exc:
            ai_result = {"report": ""}
            ai_error = str(exc)
        if progress_callback:
            progress_callback(90)
        return {
            "repository_url": repository_url,
            "mode": mode,
            "summary": scan["summary"],
            "repository_intelligence": extract_repository_intelligence(scan["summary"]),
            "reviewed_files": build_ui_file_payload(scan["files"]),
            "pipeline_files": [{"path": item["path"], "line_count": item["line_count"]} for item in scan["pipeline_files"]],
            "local_analysis": scan["local_analysis"],
            "ai_report": ai_result.get("report", ""),
            "ai_release_readiness": parse_ai_json(ai_result.get("report", "")),
            "ai_error": ai_error,
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def parse_ai_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text or "{}")
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}


def build_ui_file_payload(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = []
    for item in sorted(files, key=lambda file_item: file_item["path"]):
        content = item["content"]
        truncated = len(content) > MAX_UI_FILE_CHARS
        payload.append(
            {
                "path": item["path"],
                "language": item["language"],
                "line_count": item["line_count"],
                "is_pipeline": item["is_pipeline"],
                "content": content[:MAX_UI_FILE_CHARS],
                "truncated": truncated,
            }
        )
    return payload


def extract_repository_intelligence(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "production_readiness_score": summary.get("production_readiness_score", {}),
        "risk_heatmap": summary.get("risk_heatmap", []),
        "architecture_diagram": summary.get("architecture_diagram", {}),
        "sprint_fix_plan": summary.get("sprint_fix_plan", []),
        "release_gate": summary.get("release_gate", {}),
        "threat_model": summary.get("threat_model", {}),
        "prompt_injection_scan": summary.get("prompt_injection_scan", []),
        "onboarding_guide": summary.get("onboarding_guide", {}),
        "release_readiness": summary.get("release_readiness", {}),
    }
