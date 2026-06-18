from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "review_service"))

from repository_review import scan_repository, validate_github_url


def test_validate_github_url_accepts_standard_https_url():
    assert validate_github_url("https://github.com/example/project") == "https://github.com/example/project.git"


def test_scan_repository_ignores_vendor_binary_and_detects_pipeline(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.js").write_text("ignored")
    (tmp_path / "app.py").write_text("def hello():\n    return 'world'\n")
    (tmp_path / "image.png").write_bytes(b"\x00\x01binary")
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("name: CI\njobs:\n  test:\n    runs-on: ubuntu-latest\n")

    result = scan_repository(tmp_path)
    paths = {item["path"] for item in result["files"]}

    assert "app.py" in paths
    assert ".github/workflows/ci.yml" in paths
    assert ".git/config" not in paths
    assert "node_modules/package.js" not in paths
    assert "image.png" not in paths
    assert result["summary"]["project_overview"]["pipeline_files"] == 1
    assert result["pipeline_files"][0]["path"] == ".github/workflows/ci.yml"
