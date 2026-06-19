import ast
import base64
import difflib
import hashlib
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st
from streamlit_ace import st_ace


st.set_page_config(page_title="Code Raptor", layout="wide")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
EXECUTION_SERVICE_URL = os.getenv("EXECUTION_SERVICE_URL", "http://localhost:8002")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8003")
REVIEW_SERVICE_URL = os.getenv("REVIEW_SERVICE_URL", "http://localhost:8004")
AUTH_REQUIRED_MESSAGE = "Please login or register before using code review, file upload, or code execution."
LANGUAGE_OPTIONS = ["python", "java", "javascript", "typescript", "yaml", "json"]
LANGUAGE_LABELS = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "yaml": "YAML",
    "json": "JSON",
}
REVIEW_MODES = [
    "Security Review",
    "Performance Review",
    "Best Practices Review",
    "DevOps Review",
    "Full Repository Review",
]


def inject_dashboard_styles():
    st.markdown(
        """
        <style>
        .score-card {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 14px 16px;
            background: #ffffff;
            min-height: 112px;
        }
        .score-card .label {
            color: #4b5563;
            font-size: 0.86rem;
            margin-bottom: 6px;
        }
        .score-card .value {
            color: #111827;
            font-size: 1.45rem;
            font-weight: 700;
        }
        .score-card .hint {
            color: #6b7280;
            font-size: 0.78rem;
            margin-top: 4px;
        }
        .rating-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 3px 10px;
            font-size: 0.78rem;
            font-weight: 700;
            color: white;
            background: #2563eb;
        }
        .landing-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 2px 0 18px 0;
        }
        .landing-brand {
            color: #0f172a;
            font-size: 1.35rem;
            font-weight: 900;
        }
        .landing-hero-band {
            border: 1px solid #bed7ff;
            border-radius: 8px;
            padding: 34px;
            background:
                radial-gradient(circle at 10% 20%, rgba(45, 212, 191, 0.22), transparent 28%),
                radial-gradient(circle at 78% 12%, rgba(249, 115, 22, 0.18), transparent 28%),
                linear-gradient(135deg, #08111f 0%, #10294a 48%, #0f766e 100%);
            margin-bottom: 18px;
            box-shadow: 0 20px 46px rgba(15, 23, 42, 0.20);
        }
        .landing-hero-grid {
            display: grid;
            grid-template-columns: 1.02fr 0.98fr;
            gap: 26px;
            align-items: center;
        }
        .landing-kicker {
            color: #5eead4;
            font-size: 0.82rem;
            font-weight: 800;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .landing-title {
            color: #ffffff;
            font-size: 2.7rem;
            font-weight: 800;
            line-height: 1.08;
            margin-bottom: 10px;
        }
        .landing-subtitle {
            color: #dbeafe;
            font-size: 1.05rem;
            line-height: 1.55;
            margin-bottom: 20px;
        }
        .landing-pill {
            display: inline-block;
            border: 1px solid rgba(255,255,255,0.30);
            border-radius: 8px;
            color: #ecfeff;
            background: rgba(15, 23, 42, 0.58);
            padding: 6px 12px;
            font-size: 0.82rem;
            font-weight: 650;
            margin: 0 8px 8px 0;
            backdrop-filter: blur(8px);
        }
        .hero-actions {
            margin-top: 14px;
        }
        .hero-note {
            color: #bae6fd;
            font-size: 0.86rem;
            margin-top: 10px;
        }
        .landing-visual {
            border: 1px solid rgba(255,255,255,0.30);
            border-radius: 8px;
            background: rgba(255,255,255,0.10);
            padding: 10px;
            box-shadow: 0 18px 40px rgba(0,0,0,0.28);
        }
        .landing-visual img {
            display: block;
            width: 100%;
            border-radius: 6px;
        }
        .landing-proof {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin-top: 18px;
        }
        .proof-card {
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            background: #ffffff;
            padding: 16px;
            box-shadow: 0 10px 26px rgba(15, 23, 42, 0.08);
        }
        .proof-card .proof-title {
            color: #0f172a;
            font-size: 1rem;
            font-weight: 850;
            margin-bottom: 6px;
        }
        .proof-card .proof-copy {
            color: #475569;
            font-size: 0.9rem;
            line-height: 1.45;
        }
        .landing-preview {
            border: 1px solid #d7dde7;
            border-radius: 8px;
            background: #ffffff;
            padding: 18px;
            margin: 4px 0 18px 0;
        }
        .preview-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 12px;
            margin-bottom: 14px;
        }
        .preview-title {
            color: #111827;
            font-weight: 800;
            font-size: 1rem;
        }
        .decision-badge {
            display: inline-block;
            color: #ffffff;
            background: #dc2626;
            border-radius: 8px;
            padding: 5px 10px;
            font-size: 0.78rem;
            font-weight: 800;
        }
        .preview-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 10px;
        }
        .preview-metric {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 12px;
            background: #fbfdff;
        }
        .preview-metric .metric-label {
            color: #64748b;
            font-size: 0.76rem;
            font-weight: 700;
            margin-bottom: 6px;
        }
        .preview-metric .metric-value {
            color: #111827;
            font-size: 1.35rem;
            font-weight: 850;
        }
        .preview-alert {
            border-left: 4px solid #dc2626;
            background: #fff7ed;
            padding: 10px 12px;
            margin-top: 12px;
            color: #374151;
            font-size: 0.9rem;
        }
        .landing-card {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 18px;
            background: #ffffff;
            min-height: 150px;
        }
        .landing-card h3 {
            color: #111827;
            font-size: 1.02rem;
            margin: 0 0 8px 0;
        }
        .landing-card p {
            color: #4b5563;
            font-size: 0.9rem;
            line-height: 1.45;
            margin: 0;
        }
        .signal-strip {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin: 16px 0 18px 0;
        }
        .signal-item {
            border: 1px solid #c8d7ee;
            border-radius: 8px;
            background: #eef9ff;
            padding: 14px;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.07);
        }
        .signal-item .signal-number {
            color: #2563eb;
            font-size: 1.45rem;
            font-weight: 850;
            margin-bottom: 4px;
        }
        .signal-item .signal-label {
            color: #475569;
            font-size: 0.86rem;
            line-height: 1.35;
        }
        .story-panel {
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            background: #fff7ed;
            padding: 18px;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
        }
        .story-panel h3 {
            color: #111827;
            margin: 0 0 10px 0;
            font-size: 1.05rem;
        }
        .story-panel p {
            color: #4b5563;
            margin: 0 0 10px 0;
            line-height: 1.5;
            font-size: 0.92rem;
        }
        .landing-step {
            border: 1px solid #e5e7eb;
            border-left: 4px solid #2563eb;
            border-radius: 8px;
            padding: 10px 12px;
            color: #374151;
            font-size: 0.92rem;
            margin-bottom: 10px;
            background: #ffffff;
        }
        @media (max-width: 900px) {
            .preview-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .landing-hero-grid {
                grid-template-columns: 1fr;
            }
            .signal-strip {
                grid-template-columns: 1fr;
            }
            .landing-proof {
                grid-template-columns: 1fr;
            }
            .landing-title {
                font-size: 1.8rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_dashboard_styles()


def asset_data_url(relative_path, mime_type="image/png"):
    path = Path(__file__).resolve().parent / relative_path
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def is_valid_python_code(text):
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def authenticate(email, password):
    try:
        response = requests.post(f"{AUTH_SERVICE_URL}/login", json={"email": email, "password": password})
        if response.status_code == 200:
            return response.json()
        return None
    except requests.ConnectionError:
        st.error("Auth Service is unreachable.")
        return None


def register_user(username, email, password):
    if not username or not email or not password:
        return False
    try:
        response = requests.post(
            f"{AUTH_SERVICE_URL}/register",
            json={"username": username, "email": email, "password": password},
        )
        return response.status_code == 200
    except requests.ConnectionError:
        st.error("Auth Service is unreachable.")
        return False


def load_user_reviews(username):
    try:
        response = requests.get(f"{REVIEW_SERVICE_URL}/reviews/{username}")
        if response.status_code == 200:
            tabs = response.json()
            for tab_data in tabs.values():
                fixed_language = normalize_code_language(tab_data.get("fixed_code_language", "python"))
                if tab_data.get("fixed_code") and tab_data.get("code") == tab_data.get("fixed_code"):
                    tab_data["code_language"] = fixed_language
                else:
                    tab_data.setdefault("code_language", "python")
                tab_data.setdefault("repository_url", "")
                tab_data.setdefault("repository_mode", "Full Repository Review")
                tab_data.setdefault("repository_job_id", "")
                tab_data.setdefault("repository_review_status", None)
                tab_data.setdefault("repository_review_result", None)
            return tabs
        return {}
    except requests.ConnectionError:
        st.error("Review Service is unreachable.")
        return {}


def save_review(username, tab_id, tab_data):
    if not username:
        return None
    try:
        payload = {
            "id": tab_id,
            "code": tab_data["code"],
            "review_output": tab_data["review_output"],
            "run_output": tab_data["run_output"],
            "fixed_code": tab_data["fixed_code"],
            "fixed_code_language": tab_data.get("fixed_code_language", "python"),
            "timestamp": tab_data["timestamp"],
        }
        response = requests.post(f"{REVIEW_SERVICE_URL}/reviews/{username}", json=payload)
        if response.status_code == 200:
            analysis = response.json().get("analysis")
            if analysis:
                st.session_state["tabs"][tab_id]["analysis"] = analysis
            return analysis
        return None
    except requests.ConnectionError:
        return None


def create_new_tab():
    new_tab_id = str(uuid.uuid4())
    st.session_state["current_tab"] = new_tab_id
    st.session_state["tabs"][new_tab_id] = {
        "code": "",
        "review_output": "",
        "run_output": "",
        "fixed_code": "",
        "fixed_code_language": "python",
        "code_language": "python",
        "analysis": None,
        "repository_url": "",
        "repository_mode": "Full Repository Review",
        "repository_job_id": "",
        "repository_review_status": None,
        "repository_review_result": None,
        "editor_key": 0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if st.session_state.get("username"):
        save_review(st.session_state["username"], new_tab_id, st.session_state["tabs"][new_tab_id])


def delete_tab(tab_id):
    if tab_id not in st.session_state["tabs"]:
        return

    if tab_id == st.session_state["current_tab"]:
        remaining_tabs = [key for key in st.session_state["tabs"] if key != tab_id]
        if remaining_tabs:
            st.session_state["current_tab"] = remaining_tabs[0]
        else:
            create_new_tab()

    if st.session_state.get("username"):
        try:
            requests.delete(f"{REVIEW_SERVICE_URL}/reviews/{tab_id}")
        except requests.ConnectionError:
            pass

    del st.session_state["tabs"][tab_id]


def extract_code_from_image_with_genai(uploaded_image):
    try:
        files = {"file": (uploaded_image.name, uploaded_image.getvalue(), uploaded_image.type)}
        response = requests.post(f"{AI_SERVICE_URL}/extract", files=files)
        if response.status_code == 200:
            return response.json().get("extracted_code", "")
        st.error(f"Error from AI Service: {response.text}")
        return ""
    except Exception as e:
        st.error(f"Error extracting code from image: {str(e)}")
        return ""


def run_code(code, tab_id, language="python"):
    try:
        response = requests.post(
            f"{EXECUTION_SERVICE_URL}/run",
            json={"code": code, "tab_id": tab_id, "language": normalize_code_language(language)},
        )
        if response.status_code == 200:
            return response.json().get("output", "")
        return f"Error from Execution Service: {response.text}"
    except Exception as e:
        return f"Error: {str(e)}"


def load_analysis(tab_id):
    try:
        response = requests.get(f"{REVIEW_SERVICE_URL}/api/analysis/{tab_id}")
        if response.status_code == 200:
            analysis = response.json()
            st.session_state["tabs"][tab_id]["analysis"] = analysis
            return analysis
    except requests.ConnectionError:
        pass
    return st.session_state["tabs"].get(tab_id, {}).get("analysis")


def get_metrics_section(analysis):
    if not analysis:
        return {}
    metrics = analysis.get("metrics", {})
    if "metrics" in metrics:
        return metrics["metrics"]
    return metrics


def get_variable_section(analysis):
    if not analysis:
        return {}
    metrics = analysis.get("metrics", {})
    if "variable_analysis" in metrics:
        return metrics.get("variable_analysis", {})
    return analysis.get("variables", {})


def get_function_section(analysis):
    if not analysis:
        return {}
    metrics = analysis.get("metrics", {})
    if "function_analysis" in metrics:
        return metrics.get("function_analysis", {})
    return analysis.get("functions", {})


def get_recommendations_section(analysis):
    if not analysis:
        return []
    recommendations = analysis.get("recommendations", [])
    if isinstance(recommendations, dict):
        return recommendations.get("recommendations", [])
    return recommendations


def numeric_score(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_code_language(language):
    language = (language or "text").strip().lower()
    aliases = {
        "py": "python",
        "yml": "yaml",
        "js": "javascript",
        "ts": "typescript",
        "c++": "cpp",
    }
    return aliases.get(language, language or "text")


def is_python_language(language):
    return normalize_code_language(language) == "python"


def language_from_filename(filename):
    suffix = os.path.splitext(filename or "")[1].lower()
    mapping = {
        ".py": "python",
        ".java": "java",
        ".js": "javascript",
        ".ts": "typescript",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
    }
    return mapping.get(suffix, "python")


def score_color(score):
    score = numeric_score(score)
    if score >= 85:
        return "#16a34a"
    if score >= 70:
        return "#2563eb"
    if score >= 50:
        return "#d97706"
    return "#dc2626"


def render_score_card(label, value, hint="", max_value=100):
    score = numeric_score(value)
    progress_value = max(0, min(100, score)) / max_value
    st.markdown(
        f"""
        <div class="score-card">
            <div class="label">{label}</div>
            <div class="value" style="color:{score_color(score)}">{round(score, 2)}</div>
            <div class="hint">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(progress_value)


def render_number_card(label, value, hint=""):
    st.markdown(
        f"""
        <div class="score-card">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="hint">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_code_diff(original_code, fixed_code):
    if not fixed_code:
        return ""
    return "\n".join(
        difflib.unified_diff(
            original_code.splitlines(),
            fixed_code.splitlines(),
            fromfile="Current code",
            tofile="Fixed code",
            lineterm="",
        )
    )


def build_review_report(tab_id, tab_data):
    analysis = tab_data.get("analysis") or {}
    metrics = get_metrics_section(analysis)
    variables = get_variable_section(analysis)
    functions = get_function_section(analysis)
    memory = analysis.get("memory", {})
    performance = analysis.get("performance", {})
    health = analysis.get("health", {})
    recommendations = get_recommendations_section(analysis)
    diff = build_code_diff(tab_data.get("code", ""), tab_data.get("fixed_code", ""))
    fixed_code_language = normalize_code_language(tab_data.get("fixed_code_language", "python"))

    lines = [
        "# Code Raptor Review Report",
        "",
        f"- Review ID: `{tab_id}`",
        f"- Generated At: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- Saved At: `{tab_data.get('timestamp', '')}`",
        "",
        "## Easy Summary",
        "",
        f"- Overall Code Health: {health.get('score', 'N/A')} {health.get('rating', '')}",
        f"- Easy To Maintain: {metrics.get('maintainability_score', 'N/A')}",
        f"- Code Cleanliness: {metrics.get('code_quality_score', 'N/A')}",
        f"- Cleanup Needed: {metrics.get('technical_debt_score', 'N/A')}",
        f"- Memory Safety: {memory.get('score', 'N/A')}",
        f"- Speed Score: {performance.get('score', 'N/A')}",
        "",
        "## Code Metrics",
        "",
        f"- LOC: {metrics.get('loc', 0)}",
        f"- Classes: {metrics.get('classes', 0)}",
        f"- Functions: {metrics.get('functions', functions.get('total', 0))}",
        f"- Variables: {metrics.get('variables', variables.get('total', 0))}",
        f"- Imports: {metrics.get('imports', 0)}",
        f"- Logic Complexity: {metrics.get('cyclomatic_complexity', 0)}",
        f"- Comment Percentage: {metrics.get('comment_percentage', 0)}%",
        "",
        "## Variable Analysis",
        "",
        f"- Total: {variables.get('total', 0)}",
        f"- Global: {variables.get('global', 0)}",
        f"- Local: {variables.get('local', 0)}",
        f"- Unused: {variables.get('unused', 0)}",
        f"- Unused Names: {', '.join(variables.get('unused_names', [])) or 'None'}",
        "",
        "## AI Review",
        "",
        tab_data.get("review_output", "No AI review available."),
        "",
        "## Suggestions To Improve The Code",
        "",
    ]

    if recommendations:
        for recommendation in recommendations:
            if isinstance(recommendation, dict):
                lines.append(
                    f"- [{recommendation.get('priority', 'medium')}] "
                    f"{recommendation.get('category', 'general')}: {recommendation.get('message', '')}"
                )
            else:
                lines.append(f"- {recommendation}")
    else:
        lines.append("- No recommendations available.")

    lines.extend(["", "## Fixed Code Diff", "", "```diff", diff or "No fixed-code diff available.", "```"])

    if tab_data.get("fixed_code"):
        lines.extend(["", "## Fixed Code", "", f"```{fixed_code_language}", tab_data["fixed_code"], "```"])

    if tab_data.get("run_output"):
        lines.extend(["", "## Last Run Output", "", "```text", tab_data["run_output"], "```"])

    return "\n".join(lines)


def summarize_ai_error(response):
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text

    detail_text = str(detail)
    if response.status_code == 429 or "quota" in detail_text.lower() or "rate" in detail_text.lower():
        return (
            "The AI reviewer is temporarily unavailable because an API limit was reached. The app still checked "
            "your code locally and created the code health, memory, speed, and cleanup suggestions."
        )
    return f"AI Service error: {detail_text}"


def build_static_review_feedback(analysis, reason):
    metrics = get_metrics_section(analysis)
    variables = get_variable_section(analysis)
    functions = get_function_section(analysis)
    memory = analysis.get("memory", {}) if analysis else {}
    performance = analysis.get("performance", {}) if analysis else {}
    health = analysis.get("health", {}) if analysis else {}
    recommendations = get_recommendations_section(analysis)

    lines = [
        "### Code Review",
        "",
        reason,
        "",
        "AI review is temporarily unavailable, so Code Raptor used its built-in code checker.",
        "",
        "#### Summary",
        f"- Overall Code Health: {health.get('score', 'N/A')} {health.get('rating', '')}",
        f"- Easy To Maintain: {metrics.get('maintainability_score', 'N/A')}",
        f"- Cleanup Needed: {metrics.get('technical_debt_score', 'N/A')}",
        f"- Logic Complexity: {metrics.get('cyclomatic_complexity', 'N/A')}",
        f"- Variables: {variables.get('total', 0)} total, {variables.get('unused', 0)} unused",
        f"- Functions: {functions.get('total', 0)} total",
        f"- Memory Score: {memory.get('score', 'N/A')}",
        f"- Performance Score: {performance.get('score', 'N/A')}",
        "",
        "#### Suggestions",
    ]

    if recommendations:
        for item in recommendations[:8]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('message', '')}")
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- No high-impact local recommendations were detected.")

    if variables.get("unused_names"):
        lines.extend(["", "#### Unused Variables", f"- {', '.join(variables['unused_names'])}"])

    if functions.get("refactoring_opportunities"):
        lines.append("")
        lines.append("#### Code Cleanup Ideas")
        for item in functions["refactoring_opportunities"]:
            lines.append(f"- {item}")

    return "\n".join(lines)


def review_code(code, tab_id, mode="Full Repository Review"):
    if not st.session_state.get("username"):
        st.warning(AUTH_REQUIRED_MESSAGE)
        return

    try:
        response = requests.post(f"{AI_SERVICE_URL}/review", json={"code": code, "mode": mode})
        if response.status_code == 200:
            data = response.json()
            st.session_state["tabs"][tab_id]["review_output"] = data.get("review_output", "")
            fixed_code = data.get("fixed_code", "")
            fixed_code_language = normalize_code_language(data.get("fixed_code_language", "text"))
            if fixed_code and (not is_python_language(fixed_code_language) or is_valid_python_code(fixed_code)):
                st.session_state["tabs"][tab_id]["fixed_code"] = fixed_code
                st.session_state["tabs"][tab_id]["fixed_code_language"] = fixed_code_language
            else:
                st.session_state["tabs"][tab_id]["fixed_code"] = ""
                st.session_state["tabs"][tab_id]["fixed_code_language"] = fixed_code_language
                if fixed_code:
                    st.warning("The AI reviewer returned invalid Python, so it was not applied.")

            if st.session_state.get("username"):
                save_review(st.session_state["username"], tab_id, st.session_state["tabs"][tab_id])
                load_analysis(tab_id)
        else:
            reason = summarize_ai_error(response)
            analysis = save_review(st.session_state["username"], tab_id, st.session_state["tabs"][tab_id])
            if analysis:
                st.session_state["tabs"][tab_id]["review_output"] = build_static_review_feedback(analysis, reason)
                st.session_state["tabs"][tab_id]["fixed_code"] = ""
                st.session_state["tabs"][tab_id]["fixed_code_language"] = "text"
                save_review(st.session_state["username"], tab_id, st.session_state["tabs"][tab_id])
                st.warning(reason)
            else:
                st.error(reason)
    except Exception as e:
        st.error(f"Error during code review: {str(e)}")


def generate_corrected_file(code, mode="Full Repository Review"):
    try:
        response = requests.post(
            f"{AI_SERVICE_URL}/review",
            json={"code": code, "mode": mode},
            timeout=120,
        )
        if response.status_code == 200:
            data = response.json()
            fixed_code = data.get("fixed_code", "")
            fixed_language = normalize_code_language(data.get("fixed_code_language", "text"))
            if fixed_code:
                return {
                    "fixed_code": fixed_code,
                    "fixed_code_language": fixed_language,
                    "review_output": data.get("review_output", ""),
                }, None
            return None, "AI reviewed the file but did not return corrected code."
        return None, summarize_ai_error(response)
    except requests.ConnectionError:
        return None, "AI Service is unreachable."
    except Exception as exc:
        return None, str(exc)


def start_repository_review(repository_url, mode):
    try:
        response = requests.post(
            f"{REVIEW_SERVICE_URL}/review/repository",
            json={
                "repository_url": repository_url,
                "mode": mode,
                "username": st.session_state.get("username") or "anonymous",
            },
            timeout=20,
        )
        if response.status_code == 202:
            return response.json(), None
        return None, summarize_service_error(response)
    except requests.ConnectionError:
        return None, "Review Service is unreachable."
    except Exception as exc:
        return None, str(exc)


def get_repository_review_status(job_id):
    try:
        response = requests.get(f"{REVIEW_SERVICE_URL}/review/status/{job_id}", timeout=15)
        if response.status_code == 200:
            return response.json(), None
        return None, summarize_service_error(response)
    except requests.ConnectionError:
        return None, "Review Service is unreachable."
    except Exception as exc:
        return None, str(exc)


def get_repository_review_result(job_id):
    try:
        response = requests.get(f"{REVIEW_SERVICE_URL}/review/result/{job_id}", timeout=20)
        if response.status_code == 200:
            return response.json(), None
        if response.status_code == 202:
            return None, None
        return None, summarize_service_error(response)
    except requests.ConnectionError:
        return None, "Review Service is unreachable."
    except Exception as exc:
        return None, str(exc)


def summarize_service_error(response):
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    if isinstance(detail, dict):
        error = detail.get("error", "")
        suggestions = detail.get("suggestions", [])
        if suggestions:
            return f"{error}\n\nSuggestions:\n" + "\n".join(f"- {item}" for item in suggestions)
    return str(detail)


def render_error_suggestions(suggestions):
    if not suggestions:
        return
    st.markdown("Suggestions")
    for suggestion in suggestions:
        st.write(f"- {suggestion}")


def build_repository_report_download(result):
    if not result:
        return ""
    payload = result.get("result", result)
    intelligence = payload.get("repository_intelligence", {})
    release_readiness = intelligence.get("release_readiness", {})
    lines = [
        "# AI Release Readiness Report",
        "",
        f"- Repository: `{payload.get('repository_url', '')}`",
        f"- Mode: `{payload.get('mode', '')}`",
        f"- Generated At: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## Dashboard JSON",
        "",
        "```json",
        json_dumps(release_readiness),
        "```",
        "",
        "## Reviewed Files",
        "",
        "```json",
        json_dumps(
            [
                {
                    "path": item.get("path"),
                    "language": item.get("language"),
                    "line_count": item.get("line_count"),
                    "is_pipeline": item.get("is_pipeline"),
                }
                for item in payload.get("reviewed_files", [])
            ]
        ),
        "```",
    ]
    return "\n".join(lines)


def json_dumps(value):
    import json

    return json.dumps(value, indent=2)


def render_repository_intelligence(payload):
    intelligence = payload.get("repository_intelligence", {})
    release_readiness = intelligence.get("release_readiness", {})
    heatmap = intelligence.get("risk_heatmap", [])
    prompt_injection_scan = intelligence.get("prompt_injection_scan", [])

    if release_readiness:
        st.markdown("#### AI Release Readiness")
        cards = release_readiness.get("dashboard_cards", [])
        if cards:
            cols = st.columns(min(4, len(cards)))
            for index, card in enumerate(cards[:4]):
                cols[index].metric(
                    card.get("label", "Metric"),
                    f"{card.get('value', 'N/A')}{card.get('unit', '')}",
                    card.get("status", ""),
                )
        scores = release_readiness.get("scores", {})
        if scores:
            score_cols = st.columns(5)
            labels = [
                ("Security", "security"),
                ("Performance", "performance"),
                ("Deployment", "deployment"),
                ("Cost", "cost_optimization"),
                ("Maintainability", "maintainability"),
            ]
            for index, (label, key) in enumerate(labels):
                score_cols[index].metric(label, scores.get(key, "N/A"))
        if release_readiness.get("blockers"):
            st.error(f"Release Decision: {release_readiness.get('decision', 'UNKNOWN')}")
            st.table([{"Blocker": item} for item in release_readiness["blockers"]])
        else:
            st.success(f"Release Decision: {release_readiness.get('decision', 'UNKNOWN')}")
        predictions = release_readiness.get("predictions", {})
        if predictions:
            st.table(
                [
                    {"Prediction": "Production Failure Risk", "Value": predictions.get("production_failure_risk", "N/A")},
                    {"Prediction": "Deployment Failure Probability", "Value": f"{predictions.get('deployment_failure_probability', 'N/A')}%"},
                    {"Prediction": "Cloud Cost Waste", "Value": predictions.get("cloud_cost_waste", "N/A")},
                    {"Prediction": "Performance Bottlenecks", "Value": len(predictions.get("performance_bottlenecks", []))},
                ]
            )
        if release_readiness.get("fix_now"):
            st.markdown("#### Fix Now")
            st.table(
                [
                    {
                        "File": item.get("file"),
                        "Issue": item.get("issue"),
                        "Risk": item.get("risk_level"),
                        "Impact": item.get("impact"),
                        "Suggestion": item.get("exact_fix"),
                    }
                    for item in release_readiness["fix_now"][:8]
                ]
            )
            for index, item in enumerate(release_readiness["fix_now"][:5], start=1):
                if item.get("fixed_code"):
                    with st.expander(f"Fix {index}: {item.get('issue', 'Issue')}"):
                        st.caption(item.get("file", ""))
                        st.write(item.get("exact_fix", ""))
                        st.code(item["fixed_code"], language="yaml")
        else:
            st.success("No immediate release blockers were detected. Review optional details before production deployment.")

    if heatmap:
        st.markdown("#### Risk Heatmap")
        st.table(
            [
                {
                    "Severity": item.get("severity"),
                    "Score": item.get("score"),
                    "File": item.get("path"),
                    "Reason": ", ".join(item.get("reasons", [])),
                }
                for item in heatmap[:10]
            ]
        )

    if prompt_injection_scan:
        st.markdown("#### AI Safety Warnings")
        st.table(
            [
                {
                    "Severity": item.get("severity"),
                    "File": item.get("path"),
                    "Patterns": ", ".join(item.get("patterns", [])),
                    "Recommendation": item.get("recommendation"),
                }
                for item in prompt_injection_scan
            ]
        )

def render_compact_repository_overview(payload):
    summary = payload.get("summary", {})
    overview = summary.get("project_overview", {})
    languages = summary.get("languages_used", {})
    frameworks = summary.get("frameworks_detected", [])

    st.markdown("#### Repository Overview")
    cols = st.columns(4)
    cols[0].metric("Files Reviewed", overview.get("reviewed_files", 0))
    cols[1].metric("Lines Reviewed", overview.get("reviewed_lines", 0))
    cols[2].metric("Pipeline Files", overview.get("pipeline_files", 0))
    cols[3].metric("Languages", len(languages))

    if languages:
        st.caption("Languages: " + ", ".join(f"{name} ({count})" for name, count in languages.items()))
    if frameworks:
        st.caption("Detected: " + ", ".join(frameworks))


def render_optional_repository_details(payload):
    with st.expander("Show full technical details"):
        detail_tab, ai_tab = st.tabs(["Repository data", "AI JSON"])
        with detail_tab:
            st.json(payload.get("summary", {}))
        with ai_tab:
            ai_release = payload.get("ai_release_readiness") or {}
            if ai_release:
                st.json(ai_release)
            else:
                st.code(payload.get("ai_report", "No AI response available."), language="json")


def render_repository_file_viewer(payload):
    files = payload.get("reviewed_files", [])
    if not files:
        return

    st.markdown("#### Repository Files")
    path_options = [file_item["path"] for file_item in files]
    selected_path = st.selectbox(
        "Open file",
        path_options,
        key=f"repo_file_viewer_{payload.get('repository_url', '')}_{payload.get('mode', '')}",
    )
    selected_file = next((file_item for file_item in files if file_item["path"] == selected_path), None)
    if not selected_file:
        return

    file_issues = collect_file_issues(payload, selected_path)
    issue_count = len(file_issues)
    meta_cols = st.columns(4)
    meta_cols[0].metric("Lines", selected_file.get("line_count", 0))
    meta_cols[1].metric("Language", selected_file.get("language", "Text"))
    meta_cols[2].metric("Issues", issue_count)
    meta_cols[3].metric("Pipeline", "Yes" if selected_file.get("is_pipeline") else "No")

    issue_tab, code_tab = st.tabs(["Issues & Fixes", "File Content"])
    with issue_tab:
        if file_issues:
            st.table(
                [
                    {
                        "Issue": item.get("issue"),
                        "Risk": item.get("risk_level"),
                        "Impact": item.get("impact"),
                        "How To Fix": item.get("exact_fix"),
                    }
                    for item in file_issues
                ]
            )
            for index, item in enumerate(file_issues, start=1):
                if item.get("fixed_code"):
                    with st.expander(f"Suggested fix {index}: {item.get('issue', 'Issue')}"):
                        st.write(item.get("exact_fix", ""))
                        st.code(item["fixed_code"], language=language_for_code_block(selected_file.get("language")))
        else:
            st.success("No direct issues were mapped to this file.")

        fix_key = f"repo_file_fix_{payload.get('repository_url', '')}_{selected_path}"
        if st.button("Generate Corrected File", key=f"generate_fix_{fix_key}", type="primary"):
            with st.spinner("Generating corrected syntax and fixes..."):
                fix_result, fix_error = generate_corrected_file(
                    selected_file.get("content", ""),
                    payload.get("mode", "Full Repository Review"),
                )
            if fix_error:
                st.error(fix_error)
            else:
                st.session_state[fix_key] = fix_result
                st.success("Corrected file generated.")

        if st.session_state.get(fix_key):
            fix_result = st.session_state[fix_key]
            fixed_code = fix_result.get("fixed_code", "")
            fixed_language = fix_result.get("fixed_code_language", language_for_code_block(selected_file.get("language")))
            st.markdown("#### Corrected Version")
            before_tab, after_tab, notes_tab = st.tabs(["Current", "Corrected", "What Changed"])
            with before_tab:
                st.code(selected_file.get("content", ""), language=language_for_code_block(selected_file.get("language")))
            with after_tab:
                st.code(fixed_code, language=fixed_language)
                st.download_button(
                    "Download Corrected File",
                    data=fixed_code,
                    file_name=selected_path.split("/")[-1],
                    mime="text/plain",
                    key=f"download_fix_{fix_key}",
                    use_container_width=True,
                )
            with notes_tab:
                st.markdown(fix_result.get("review_output", "No explanation available."))

    with code_tab:
        if selected_file.get("truncated"):
            st.warning("Large file preview is truncated for performance.")
        st.code(selected_file.get("content", ""), language=language_for_code_block(selected_file.get("language")))


def collect_file_issues(payload, selected_path):
    intelligence = payload.get("repository_intelligence", {})
    release = intelligence.get("release_readiness", {})
    issues = []
    for item in release.get("fix_now", []):
        if item.get("file") == selected_path:
            issues.append(item)
    for item in intelligence.get("risk_heatmap", []):
        if item.get("path") == selected_path:
            issues.append(
                {
                    "issue": "Repository risk",
                    "risk_level": item.get("severity"),
                    "impact": ", ".join(item.get("reasons", [])),
                    "exact_fix": "Fix the listed risk before release.",
                    "fixed_code": "",
                }
            )
    for item in intelligence.get("prompt_injection_scan", []):
        if item.get("path") == selected_path:
            issues.append(
                {
                    "issue": "Prompt injection risk",
                    "risk_level": item.get("severity"),
                    "impact": ", ".join(item.get("patterns", [])),
                    "exact_fix": item.get("recommendation", "Treat repository text as untrusted AI input."),
                    "fixed_code": "",
                }
            )
    return issues


def language_for_code_block(language):
    mapping = {
        "Python": "python",
        "JavaScript": "javascript",
        "TypeScript": "typescript",
        "Java": "java",
        "YAML": "yaml",
        "JSON": "json",
        "DevOps": "yaml",
    }
    return mapping.get(language or "", "text")


def language_for_code_block_from_path(path):
    path = (path or "").lower()
    if path.endswith(".py"):
        return "python"
    if path.endswith(".js"):
        return "javascript"
    if path.endswith(".ts"):
        return "typescript"
    if path.endswith(".java"):
        return "java"
    if path.endswith(".json"):
        return "json"
    if path.endswith((".yaml", ".yml")) or "workflow" in path or "pipeline" in path or path.endswith("jenkinsfile"):
        return "yaml"
    if path.endswith("dockerfile"):
        return "dockerfile"
    return "text"


def render_ai_enrichment_warning(payload):
    ai_error = payload.get("ai_error")
    if not ai_error:
        return
    st.warning("AI enrichment was unavailable, so the dashboard used built-in repository analysis.")
    lowered = ai_error.lower()
    if "azure openai config missing" in lowered:
        render_error_suggestions([
            "Check your local .env file.",
            "Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT.",
            "Restart Docker Compose with docker compose up --build.",
        ])
    elif "name or service not known" in lowered:
        render_error_suggestions([
            "Check AZURE_OPENAI_ENDPOINT spelling.",
            "Verify the ai-service container has internet/DNS access.",
            "Restart ai-service after changing .env.",
        ])
    else:
        render_error_suggestions(["Check ai-service logs for the AI enrichment error."])


def get_sorted_tabs():
    return dict(
        sorted(
            st.session_state["tabs"].items(),
            key=lambda item: item[1]["timestamp"],
            reverse=True,
        )
    )


def init_session_state():
    if "tabs" not in st.session_state:
        st.session_state["tabs"] = {}
        create_new_tab()
    if "username" not in st.session_state:
        st.session_state["username"] = None
    if "page" not in st.session_state:
        st.session_state["page"] = "Review"
    if "auth_mode" not in st.session_state:
        st.session_state["auth_mode"] = "Login"


def apply_fixed_code(tab_id, run_after_apply=False):
    fixed_code = st.session_state["tabs"][tab_id]["fixed_code"]
    fixed_code_language = normalize_code_language(st.session_state["tabs"][tab_id].get("fixed_code_language", "python"))
    if not fixed_code:
        st.warning("No fixed code is available to apply.")
        return
    if is_python_language(fixed_code_language) and not is_valid_python_code(fixed_code):
        st.error("The suggested fixed code is not valid Python, so it was not applied.")
        return

    st.session_state["tabs"][tab_id]["code"] = fixed_code
    st.session_state["tabs"][tab_id]["code_language"] = fixed_code_language
    st.session_state["tabs"][tab_id]["editor_key"] += 1

    if run_after_apply:
        st.session_state["tabs"][tab_id]["run_output"] = run_code(fixed_code, tab_id, fixed_code_language)

    if st.session_state.get("username"):
        save_review(st.session_state["username"], tab_id, st.session_state["tabs"][tab_id])


def logout_user():
    st.session_state["username"] = None
    st.session_state["tabs"] = {}
    create_new_tab()
    st.session_state["page"] = "Login/Register"


def show_sidebar():
    with st.sidebar:
        st.title("Code Raptor")
        st.caption(f"Logged in as {st.session_state['username']}")

        if st.button("Code Review", type="primary", use_container_width=True):
            st.session_state["page"] = "Review"
            st.rerun()
        if st.button("Code Health", use_container_width=True):
            st.session_state["page"] = "Code Health"
            st.rerun()
        if st.button("About", use_container_width=True):
            st.session_state["page"] = "About"
            st.rerun()
        if st.button("Logout", use_container_width=True):
            logout_user()
            st.rerun()

        st.divider()
        st.subheader("Review History")

        if st.button("New Review", use_container_width=True):
            create_new_tab()
            st.session_state["page"] = "Review"
            st.rerun()

        if not get_sorted_tabs():
            st.caption("No saved reviews yet.")
            return

        for tab_id, tab_data in get_sorted_tabs().items():
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    f"Review from {tab_data['timestamp']}",
                    key=f"history_{tab_id}",
                    use_container_width=True,
                ):
                    st.session_state["current_tab"] = tab_id
                    st.session_state["page"] = "Review"
                    st.rerun()
            with col2:
                if st.button("X", key=f"delete_{tab_id}"):
                    delete_tab(tab_id)
                    st.rerun()


def show_about_page():
    st.title("About CodeRaptor")
    st.write(
        "CodeRaptor helps users extract code from images, run Python snippets, "
        "and get AI-powered code review feedback in one workspace."
    )

    st.subheader("Features")
    st.markdown(
        """
        - Extract code from uploaded PNG and JPG images.
        - Upload Python files directly into the editor.
        - Run Python code and view output.
        - Review code with Azure AI and apply suggested fixes.
        - View easy code health, memory, speed, cleanup, and variable checks.
        - Save review history after login.
        """
    )

    st.subheader("Project Services")
    st.markdown(
        """
        - Frontend: Streamlit interface.
        - Auth service: login and registration.
        - Execution service: code running.
        - AI service: Azure AI review and image extraction.
        - Review service: history storage.
        """
    )


def go_to_auth(mode):
    st.session_state["auth_mode"] = mode
    st.session_state["page"] = "Login/Register"
    st.rerun()


def show_landing_page():
    if st.session_state.get("username"):
        st.session_state["page"] = "Review"
        st.rerun()
        return

    nav_left, nav_right = st.columns([3, 1])
    with nav_left:
        st.markdown('<div class="landing-brand">Code Raptor</div>', unsafe_allow_html=True)
    with nav_right:
        login_col, register_col = st.columns(2)
        with login_col:
            if st.button("Login", use_container_width=True):
                go_to_auth("Login")
        with register_col:
            if st.button("Register", type="primary", use_container_width=True):
                go_to_auth("Register")

    hero_image = asset_data_url("assets/release-command-center.png")
    st.markdown(
        f"""
        <div class="landing-hero-band">
            <div class="landing-hero-grid">
                <div>
                    <div class="landing-kicker">AI release confidence for real deployments</div>
                    <div class="landing-title">Review code like production depends on it.</div>
                    <div class="landing-subtitle">
                        Code Raptor finds release blockers, risky repository files, weak deployment
                        configuration, and practical fixes before your code reaches users.
                    </div>
                    <span class="landing-pill">Repository review</span>
                    <span class="landing-pill">Pipeline safety</span>
                    <span class="landing-pill">AKS readiness</span>
                    <span class="landing-pill">Correct fix snippets</span>
                    <div class="hero-note">Built for reviewers who need a decision, not another long report.</div>
                </div>
                <div class="landing-visual">
                    <img src="{hero_image}" alt="AI release command center visual">
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="landing-proof">
            <div class="proof-card">
                <div class="proof-title">Release decision first</div>
                <div class="proof-copy">See whether a repository is approved, warning-level, or blocked before reading details.</div>
            </div>
            <div class="proof-card">
                <div class="proof-title">Issues mapped to files</div>
                <div class="proof-copy">Open the exact repo file, compare the issue, and understand where the fix belongs.</div>
            </div>
            <div class="proof-card">
                <div class="proof-title">Fixes you can use</div>
                <div class="proof-copy">Generate corrected code, YAML, Dockerfile, or pipeline snippets instead of vague advice.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_auth_page():
    if st.session_state.get("username"):
        st.session_state["page"] = "Review"
        st.rerun()
        return

    if st.button("Back to Home"):
        st.session_state["page"] = "Landing"
        st.rerun()

    st.markdown(
        """
        <div class="landing-hero-band">
            <div class="landing-kicker">Secure workspace access</div>
            <div class="landing-title">Start your release review.</div>
            <div class="landing-subtitle">
                Login to continue your saved reviews, or register to create a new Code Raptor workspace.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    form_left, form_right = st.columns([0.85, 1.15])
    with form_left:
        st.markdown(
            """
            <div class="story-panel">
                <h3>After signing in</h3>
                <p>Review pasted code, scan GitHub repositories, inspect repo files, generate fixes, and save review history.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with form_right:
        st.caption(f"Selected action: {st.session_state.get('auth_mode', 'Login')}")
        login_tab, register_tab = st.tabs(["Login", "Register"])

        with login_tab:
            email = st.text_input("Email", key="login_email")
            show_login_password = st.checkbox("Show password", key="show_login_password")
            password = st.text_input(
                "Password",
                type="default" if show_login_password else "password",
                key="login_password",
            )
            if st.button("Login", type="primary", use_container_width=True):
                login_data = authenticate(email, password)
                if login_data:
                    username = login_data.get("username", email)
                    st.session_state["username"] = username
                    st.session_state["tabs"] = load_user_reviews(username)
                    if not st.session_state["tabs"]:
                        create_new_tab()
                    st.session_state["page"] = "Review"
                    st.rerun()
                else:
                    st.error("Invalid email or password")

        with register_tab:
            new_username = st.text_input("Username", key="reg_username")
            new_email = st.text_input("Email", key="reg_email")
            show_register_password = st.checkbox("Show password", key="show_register_password")
            password_type = "default" if show_register_password else "password"
            new_password = st.text_input("Password", type=password_type, key="reg_password")
            confirm_password = st.text_input("Confirm Password", type=password_type, key="reg_confirm_password")
            if st.button("Register", type="primary", use_container_width=True):
                if new_password != confirm_password:
                    st.error("Password and confirm password do not match.")
                elif register_user(new_username, new_email, new_password):
                    st.success("Registration successful. Please login.")
                else:
                    st.error("Username or email already exists, or input is invalid.")


def get_current_tab_data():
    if not st.session_state.get("tabs"):
        create_new_tab()

    current_tab = st.session_state.get("current_tab")
    if current_tab not in st.session_state["tabs"]:
        create_new_tab()
        current_tab = st.session_state["current_tab"]

    return current_tab, st.session_state["tabs"][current_tab]


def metric_value(analysis, key, default=0):
    if not analysis:
        return default
    metrics = get_metrics_section(analysis)
    return metrics.get(key, default)


def render_analysis_cards(analysis):
    if not analysis:
        st.info("Run or save a review to generate code metrics.")
        return

    variable_analysis = get_variable_section(analysis)
    function_analysis = get_function_section(analysis)
    memory = analysis.get("memory", {})
    performance = analysis.get("performance", {})
    health = analysis.get("health", {})
    recommendations = get_recommendations_section(analysis)

    st.markdown(
        f"""
        <span class="rating-badge" style="background:{score_color(health.get('score', 0))}">
            Overall Code Health: {health.get('rating', 'Not Rated')}
        </span>
        """,
        unsafe_allow_html=True,
    )

    score_cols = st.columns(5)
    with score_cols[0]:
        render_score_card("Overall Health", health.get("score", 0), "Overall condition of the code")
    with score_cols[1]:
        render_score_card("Memory Safety", memory.get("score", 0), "Higher means fewer memory problems")
    with score_cols[2]:
        render_score_card("Speed Score", performance.get("score", 0), "Higher means fewer slow code patterns")
    with score_cols[3]:
        render_score_card("Easy To Maintain", metric_value(analysis, "maintainability_score"), "How easy it is to change later")
    with score_cols[4]:
        render_score_card("Clean Code", metric_value(analysis, "code_quality_score"), "How clean the code looks")

    number_cols = st.columns(6)
    with number_cols[0]:
        render_number_card("Total Variables", metric_value(analysis, "variables", variable_analysis.get("total", 0)), "Global + local")
    with number_cols[1]:
        render_number_card("Unused Variables", variable_analysis.get("unused", 0), "Can usually be removed")
    with number_cols[2]:
        render_number_card("Functions", metric_value(analysis, "functions", function_analysis.get("total", 0)), "Methods included")
    with number_cols[3]:
        render_number_card("Logic Complexity", metric_value(analysis, "cyclomatic_complexity"), "Lower is easier to understand")
    with number_cols[4]:
        render_number_card("Cleanup Needed", metric_value(analysis, "technical_debt_score"), "Lower is better")
    with number_cols[5]:
        render_number_card("LOC", metric_value(analysis, "loc"), "Non-empty code lines")

    detail_tab, memory_tab, performance_tab, recommendations_tab = st.tabs(
        ["Code Health", "Memory", "Speed", "Suggestions"]
    )
    with detail_tab:
        st.table(
            [
                {"Metric": "LOC", "Value": metric_value(analysis, "loc")},
                {"Metric": "Classes", "Value": metric_value(analysis, "classes")},
                {"Metric": "Functions", "Value": metric_value(analysis, "functions", function_analysis.get("total", 0))},
                {"Metric": "Imports", "Value": metric_value(analysis, "imports")},
                {"Metric": "Comment %", "Value": metric_value(analysis, "comment_percentage")},
                {"Metric": "Global Variables", "Value": variable_analysis.get("global", 0)},
                {"Metric": "Local Variables", "Value": variable_analysis.get("local", 0)},
            ]
        )
        if variable_analysis.get("unused_names"):
            st.warning(f"Unused variables: {', '.join(variable_analysis['unused_names'])}")
        if function_analysis.get("refactoring_opportunities"):
            st.write("Code Cleanup Ideas")
            st.table([{"Recommendation": item} for item in function_analysis["refactoring_opportunities"]])
    with memory_tab:
        patterns = memory.get("patterns", [])
        if patterns:
            st.table(patterns)
        else:
            st.success("No memory-heavy patterns detected.")
        if memory.get("recommendations"):
            st.write("Memory Suggestions")
            st.table([{"Recommendation": item} for item in memory["recommendations"]])
    with performance_tab:
        st.metric("Nested loops", performance.get("nested_loops", 0))
        patterns = performance.get("patterns", [])
        if patterns:
            st.table(patterns)
        else:
            st.success("No performance-heavy patterns detected.")
        if performance.get("recommendations"):
            st.write("Speed Suggestions")
            st.table([{"Recommendation": item} for item in performance["recommendations"]])
    with recommendations_tab:
        if recommendations:
            st.table(recommendations)
        else:
            st.success("No high-impact recommendations detected.")


def show_dashboard_page():
    st.title("Code Health")
    current_tab, current_tab_data = get_current_tab_data()
    analysis = current_tab_data.get("analysis") or load_analysis(current_tab)
    render_analysis_cards(analysis)
    report = build_review_report(current_tab, current_tab_data)
    st.download_button(
        "Download Code Report",
        data=report,
        file_name=f"code-raptor-report-{current_tab}.md",
        mime="text/markdown",
        use_container_width=True,
    )


def handle_upload(uploaded_file):
    if not st.session_state.get("username"):
        st.warning(AUTH_REQUIRED_MESSAGE)
        return

    file_type = uploaded_file.type
    uploaded_language = language_from_filename(uploaded_file.name)

    if uploaded_file.name.lower().endswith((".py", ".java", ".js", ".ts", ".yaml", ".yml", ".json")):
        new_code = uploaded_file.read().decode("utf-8")
        code_hash = hashlib.md5(new_code.encode()).hexdigest()

        if code_hash != st.session_state.get("last_processed_code_hash"):
            if new_code:
                tab_id = st.session_state["current_tab"]
                st.session_state["tabs"][tab_id]["code"] = new_code
                st.session_state["tabs"][tab_id]["code_language"] = uploaded_language
                st.session_state["tabs"][tab_id]["editor_key"] += 1
                if st.session_state.get("username"):
                    save_review(st.session_state["username"], tab_id, st.session_state["tabs"][tab_id])

                st.session_state["last_processed_code_hash"] = code_hash
                st.success(f"{LANGUAGE_LABELS.get(uploaded_language, uploaded_language)} file uploaded and code updated in the editor.")
                st.rerun()
            else:
                st.warning("No code detected in the uploaded file.")

    elif file_type in ["image/png", "image/jpeg"]:
        image_bytes = uploaded_file.getvalue()
        image_hash = hashlib.md5(image_bytes).hexdigest()

        if image_hash == st.session_state.get("last_processed_image_hash"):
            st.info("This image has already been processed.")
            return

        extracted_code = extract_code_from_image_with_genai(uploaded_file)
        if extracted_code:
            tab_id = st.session_state["current_tab"]
            if is_valid_python_code(extracted_code):
                st.session_state["tabs"][tab_id]["code"] = extracted_code
                st.session_state["tabs"][tab_id]["editor_key"] += 1
                st.success("Code extracted and updated in the editor.")
            else:
                st.session_state["tabs"][tab_id]["review_output"] = extracted_code
                st.warning("Extracted text does not seem like code. Stored in review section.")

            if st.session_state.get("username"):
                save_review(st.session_state["username"], tab_id, st.session_state["tabs"][tab_id])

            st.session_state["last_processed_image_hash"] = image_hash
            st.rerun()
        else:
            st.warning("No code detected in the uploaded image.")


def render_repository_review_panel(current_tab, current_tab_data):
    st.markdown("#### Repository Review")
    repo_url = st.text_input(
        "GitHub Repository URL",
        value=current_tab_data.get("repository_url", ""),
        placeholder="https://github.com/user/project",
        key=f"repo_url_{current_tab}",
    )
    mode = st.selectbox(
        "Review mode",
        REVIEW_MODES,
        index=REVIEW_MODES.index(current_tab_data.get("repository_mode", "Full Repository Review"))
        if current_tab_data.get("repository_mode", "Full Repository Review") in REVIEW_MODES
        else REVIEW_MODES.index("Full Repository Review"),
        key=f"repo_mode_{current_tab}",
    )

    st.session_state["tabs"][current_tab]["repository_url"] = repo_url
    st.session_state["tabs"][current_tab]["repository_mode"] = mode

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Review Repository", key=f"repo_review_{current_tab}", type="primary", use_container_width=True):
            if not repo_url.strip():
                st.warning("Please enter a GitHub repository URL.")
            else:
                data, error = start_repository_review(repo_url.strip(), mode)
                if error:
                    st.error(error)
                else:
                    st.session_state["tabs"][current_tab]["repository_job_id"] = data["job_id"]
                    st.session_state["tabs"][current_tab]["repository_review_status"] = data
                    st.session_state["tabs"][current_tab]["repository_review_result"] = None
                    st.success("Repository review started.")
                    st.rerun()

    job_id = st.session_state["tabs"][current_tab].get("repository_job_id")
    if not job_id:
        return

    current_status = st.session_state["tabs"][current_tab].get("repository_review_status") or {}
    if current_status.get("status") in {"queued", "running"}:
        status, error = get_repository_review_status(job_id)
        if error:
            st.error(error)
        elif status:
            st.session_state["tabs"][current_tab]["repository_review_status"] = status
            if status.get("status") == "completed":
                result, result_error = get_repository_review_result(job_id)
                if result_error:
                    st.error(result_error)
                elif result:
                    st.session_state["tabs"][current_tab]["repository_review_result"] = result

    with col2:
        if st.button("Refresh Repository Status", key=f"repo_refresh_{current_tab}", use_container_width=True):
            status, error = get_repository_review_status(job_id)
            if error:
                st.error(error)
            elif status:
                st.session_state["tabs"][current_tab]["repository_review_status"] = status
                if status.get("status") == "completed":
                    result, result_error = get_repository_review_result(job_id)
                    if result_error:
                        st.error(result_error)
                    elif result:
                        st.session_state["tabs"][current_tab]["repository_review_result"] = result
                st.rerun()

    status = st.session_state["tabs"][current_tab].get("repository_review_status")
    if status:
        progress = int(status.get("progress", 0))
        st.progress(progress / 100)
        st.caption(f"Job {job_id}: {status.get('status', 'unknown')} ({progress}%)")
        if status.get("error"):
            st.error(status["error"])
            render_error_suggestions(status.get("suggestions", []))

    result = st.session_state["tabs"][current_tab].get("repository_review_result")
    if result:
        payload = result.get("result", {})
        render_compact_repository_overview(payload)
        render_ai_enrichment_warning(payload)
        render_repository_intelligence(payload)
        render_repository_file_viewer(payload)
        render_optional_repository_details(payload)
        st.download_button(
            "Download Release Readiness JSON",
            data=build_repository_report_download(result),
            file_name=f"repository-review-{job_id}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    elif status and status.get("status") in {"queued", "running"}:
        time.sleep(3)
        st.rerun()


def show_review_page():
    if not st.session_state.get("username"):
        st.warning(AUTH_REQUIRED_MESSAGE)
        st.session_state["page"] = "Login/Register"
        show_auth_page()
        return

    current_tab, current_tab_data = get_current_tab_data()

    st.title("Code Review")

    render_repository_review_panel(current_tab, current_tab_data)
    st.divider()

    current_language = normalize_code_language(current_tab_data.get("code_language", "python"))
    if current_language not in LANGUAGE_OPTIONS:
        current_language = "python"
    selected_language = st.selectbox(
        "Code language",
        LANGUAGE_OPTIONS,
        index=LANGUAGE_OPTIONS.index(current_language),
        format_func=lambda item: LANGUAGE_LABELS.get(item, item.title()),
        key=f"language_{current_tab}",
    )
    if selected_language != current_tab_data.get("code_language", "python"):
        st.session_state["tabs"][current_tab]["code_language"] = selected_language
        current_tab_data["code_language"] = selected_language
        if st.session_state.get("username"):
            save_review(st.session_state["username"], current_tab, st.session_state["tabs"][current_tab])

    editor_language = normalize_code_language(current_tab_data.get("code_language", selected_language))
    code = st_ace(
        language=editor_language,
        theme="monokai",
        height=300,
        value=current_tab_data["code"],
        key=f"editor_{current_tab}_{current_tab_data['editor_key']}",
    )

    uploaded_file = st.file_uploader(
        "Upload a file (Code or Image)",
        type=["py", "java", "js", "ts", "yaml", "yml", "json", "png", "jpg", "jpeg"],
    )
    st.caption("For images, wait while the app extracts code. To edit manually after upload, clear the uploaded file.")

    if uploaded_file is not None:
        handle_upload(uploaded_file)

    if code != current_tab_data["code"]:
        if st.session_state.get("username"):
            st.session_state["tabs"][current_tab]["code"] = code
            st.session_state["tabs"][current_tab]["code_language"] = selected_language
            save_review(st.session_state["username"], current_tab, st.session_state["tabs"][current_tab])
        else:
            st.warning(AUTH_REQUIRED_MESSAGE)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Run Code", key=f"run_{current_tab}", use_container_width=True):
            if not st.session_state.get("username"):
                st.warning(AUTH_REQUIRED_MESSAGE)
            elif code.strip():
                current_language = normalize_code_language(st.session_state["tabs"][current_tab].get("code_language", "python"))
                result = run_code(code, current_tab, current_language)
                st.session_state["tabs"][current_tab]["run_output"] = result
                if st.session_state.get("username"):
                    save_review(st.session_state["username"], current_tab, st.session_state["tabs"][current_tab])
            else:
                st.warning("Please enter some code.")

    with col2:
        if st.button("Review Code", key=f"review_{current_tab}", type="primary", use_container_width=True):
            if not st.session_state.get("username"):
                st.warning(AUTH_REQUIRED_MESSAGE)
            elif code.strip():
                review_code(code, current_tab, st.session_state["tabs"][current_tab].get("repository_mode", "Full Repository Review"))
            else:
                st.warning("Please enter some code.")

    if current_tab_data["run_output"]:
        st.markdown("#### Output")
        st.code(current_tab_data["run_output"])

    if current_tab_data["review_output"]:
        st.markdown("#### Review Feedback")
        st.markdown(current_tab_data["review_output"])

        if current_tab_data["fixed_code"]:
            fixed_code_language = normalize_code_language(current_tab_data.get("fixed_code_language", "python"))
            st.markdown("#### Fixed Code Review")
            preview_tab, diff_tab = st.tabs(["Before and After", "Exact Changes"])
            with preview_tab:
                before_col, after_col = st.columns(2)
                with before_col:
                    st.caption("Current Code")
                    st.code(current_tab_data["code"], language=fixed_code_language)
                with after_col:
                    st.caption(f"Fixed Code ({fixed_code_language})")
                    st.code(current_tab_data["fixed_code"], language=fixed_code_language)
            with diff_tab:
                diff = build_code_diff(current_tab_data["code"], current_tab_data["fixed_code"])
                st.code(diff or "No differences detected.", language="diff")

            button_label = "Apply & Run Fixed Code" if fixed_code_language != "yaml" else "Apply & Validate YAML"
            if st.button(button_label, key=f"apply_{current_tab}"):
                apply_fixed_code(current_tab, run_after_apply=True)
                st.rerun()

    st.markdown("#### Code Health")
    render_analysis_cards(current_tab_data.get("analysis"))
    report = build_review_report(current_tab, current_tab_data)
    st.download_button(
        "Download Code Report",
        data=report,
        file_name=f"code-raptor-report-{current_tab}.md",
        mime="text/markdown",
        use_container_width=True,
    )


init_session_state()

if not st.session_state.get("username"):
    if st.session_state.get("page") == "Login/Register":
        show_auth_page()
    else:
        st.session_state["page"] = "Landing"
        show_landing_page()
else:
    show_sidebar()

    if st.session_state["page"] == "About":
        show_about_page()
    elif st.session_state["page"] == "Code Health":
        show_dashboard_page()
    else:
        show_review_page()
