from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "review_service"))

from analyzers.code_metrics import analyze_code, calculate_health_score


def test_variable_analyzer_counts_global_local_and_unused_variables():
    code = """
GLOBAL_VALUE = 1

def sample(item):
    used = item + GLOBAL_VALUE
    unused = 2
    return used
"""
    result = analyze_code(code)

    assert result["variables"]["total"] >= 4
    assert result["variables"]["global"] == 1
    assert result["variables"]["local"] >= 3
    assert "unused" in result["variables"]["unused_names"]


def test_complexity_analyzer_counts_branches_and_nested_loops():
    code = """
def work(items):
    total = 0
    for item in items:
        for other in items:
            if item == other or other > 10:
                total += other
    return total
"""
    result = analyze_code(code)

    assert result["metrics"]["cyclomatic_complexity"] >= 5
    assert result["performance"]["nested_loops"] == 1
    assert any(pattern["type"] == "nested_loop" for pattern in result["performance"]["patterns"])


def test_health_score_calculator_uses_weighted_components_and_rating():
    result = calculate_health_score(
        maintainability=90,
        security=90,
        performance=80,
        code_quality=80,
        documentation=70,
    )

    assert result["score"] == 83.5
    assert result["rating"] == "Good"


def test_performance_analyzer_detects_repeated_database_calls():
    code = """
def load(ids, cursor):
    rows = []
    for item_id in ids:
        cursor.execute("select * from items where id=%s", (item_id,))
        rows.append(cursor.fetchone())
    return rows
"""
    result = analyze_code(code)

    assert any(pattern["type"] == "repeated_io_call" for pattern in result["performance"]["patterns"])
    assert any(rec["category"] == "performance" for rec in result["recommendations"])


def test_memory_analyzer_detects_large_reads_and_allocations():
    code = """
def read_all(path):
    with open(path) as handle:
        data = handle.readlines()
    return [line.strip() for line in data]
"""
    result = analyze_code(code)

    pattern_types = {pattern["type"] for pattern in result["memory"]["patterns"]}
    assert "large_read" in pattern_types
    assert "list_comprehension" in pattern_types
