import ast
import io
import tokenize
from dataclasses import dataclass, field
from typing import Any, Union


TOO_MANY_PARAMETERS = 5
LONG_METHOD_LINES = 50


@dataclass
class VariableStats:
    total: int = 0
    global_count: int = 0
    local_count: int = 0
    unused: int = 0
    names: set[str] = field(default_factory=set)
    assigned: dict[str, int] = field(default_factory=dict)
    used: set[str] = field(default_factory=set)


class MetricVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.variables = VariableStats()
        self.functions: list[dict[str, Any]] = []
        self.classes = 0
        self.imports = 0
        self.complexity = 1
        self.scope_depth = 0
        self.loop_depth = 0
        self.nested_loops = 0
        self.memory_patterns: list[dict[str, Any]] = []
        self.performance_patterns: list[dict[str, Any]] = []

    def visit_Import(self, node: ast.Import) -> Any:
        self.imports += len(node.names)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        self.imports += len(node.names)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.classes += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._record_function(node)
        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._record_function(node)
        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1

    def visit_Name(self, node: ast.Name) -> Any:
        if isinstance(node.ctx, ast.Store):
            self._assign_name(node.id, node.lineno)
        elif isinstance(node.ctx, ast.Load):
            self.variables.used.add(node.id)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> Any:
        self._assign_name(node.arg, getattr(node, "lineno", 0))

    def visit_For(self, node: ast.For) -> Any:
        self._complex_branch()
        if self.loop_depth > 0:
            self.nested_loops += 1
            self.performance_patterns.append(
                issue("nested_loop", node.lineno, "Nested loop may create O(n^2) runtime.")
            )
        self.loop_depth += 1
        self._detect_repeated_allocation(node)
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_AsyncFor(self, node: ast.AsyncFor) -> Any:
        self.visit_For(node)

    def visit_While(self, node: ast.While) -> Any:
        self._complex_branch()
        if self.loop_depth > 0:
            self.nested_loops += 1
            self.performance_patterns.append(
                issue("nested_loop", node.lineno, "Nested loop may create O(n^2) runtime.")
            )
        self.loop_depth += 1
        self._detect_repeated_allocation(node)
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_If(self, node: ast.If) -> Any:
        self._complex_branch()
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        self._complex_branch()
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        self.complexity += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> Any:
        self.complexity += len(node.handlers)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> Any:
        self._complex_branch()
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> Any:
        self._visit_comprehension(node, "list_comprehension")

    def visit_SetComp(self, node: ast.SetComp) -> Any:
        self._visit_comprehension(node, "set_comprehension")

    def visit_DictComp(self, node: ast.DictComp) -> Any:
        self._visit_comprehension(node, "dict_comprehension")

    def visit_Call(self, node: ast.Call) -> Any:
        name = call_name(node.func)
        short_name = name.split(".")[-1]
        if name in {"list", "dict", "set", "tuple"} and node.args:
            self.memory_patterns.append(
                issue("eager_collection_copy", node.lineno, f"`{name}()` may copy a large collection into memory.")
            )
        if short_name in {"read", "readlines"}:
            self.memory_patterns.append(
                issue("large_read", node.lineno, "Whole-file read can load large data into memory.")
            )
        if short_name in {"sleep", "wait", "result", "join"}:
            self.performance_patterns.append(
                issue("blocking_operation", node.lineno, f"`{name}` can block request processing.")
            )
        if short_name == "fetchall":
            self.memory_patterns.append(
                issue("large_result_fetch", node.lineno, "`fetchall()` can materialize large result sets in memory.")
            )
            self.performance_patterns.append(
                issue("inefficient_api_usage", node.lineno, "Prefer paginated or streaming fetches for large result sets.")
            )
        if (short_name in {"execute", "fetchone", "fetchall"} or name in {"requests.get", "requests.post"}) and self.loop_depth:
            self.performance_patterns.append(
                issue("repeated_io_call", node.lineno, f"`{name}` inside a loop can cause repeated database/API calls.")
            )
        self.generic_visit(node)

    def _record_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
        params = len(node.args.args) + len(node.args.kwonlyargs) + len(node.args.posonlyargs)
        if node.args.vararg:
            params += 1
        if node.args.kwarg:
            params += 1
        end_line = getattr(node, "end_lineno", node.lineno)
        line_count = max(1, end_line - node.lineno + 1)
        flags = []
        if line_count > LONG_METHOD_LINES:
            flags.append("long_method")
        if params > TOO_MANY_PARAMETERS:
            flags.append("too_many_parameters")
        self.functions.append(
            {
                "name": node.name,
                "line": node.lineno,
                "lines": line_count,
                "parameters": params,
                "flags": flags,
            }
        )
        self._detect_duplicate_computations(node)

    def _assign_name(self, name: str, line: int) -> None:
        self.variables.names.add(name)
        self.variables.assigned.setdefault(name, line)
        if self.scope_depth == 0:
            self.variables.global_count += 1
        else:
            self.variables.local_count += 1

    def _complex_branch(self) -> None:
        self.complexity += 1

    def _visit_comprehension(self, node: ast.AST, pattern: str) -> None:
        generators = getattr(node, "generators", [])
        self.complexity += len(generators)
        if len(generators) > 1:
            self.nested_loops += 1
            self.performance_patterns.append(
                issue("nested_comprehension", node.lineno, "Nested comprehension may create quadratic work.")
            )
        self.memory_patterns.append(
            issue(pattern, node.lineno, "Comprehension creates a collection eagerly; use a generator for large data.")
        )
        self.generic_visit(node)

    def _detect_repeated_allocation(self, node: Union[ast.For, ast.While]) -> None:
        for child in ast.walk(node):
            if child is node:
                continue
            if isinstance(child, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
                self.memory_patterns.append(
                    issue("repeated_allocation", getattr(child, "lineno", node.lineno), "Collection allocated inside a loop.")
                )

    def _detect_duplicate_computations(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
        seen: dict[str, int] = {}
        for child in ast.walk(node):
            if isinstance(child, (ast.BinOp, ast.BoolOp, ast.Compare, ast.Call)):
                marker = ast.dump(child, include_attributes=False)
                if marker in seen:
                    self.performance_patterns.append(
                        issue(
                            "duplicate_computation",
                            getattr(child, "lineno", node.lineno),
                            "Repeated expression or call detected; store the result once if it is expensive.",
                        )
                    )
                    return
                seen[marker] = getattr(child, "lineno", node.lineno)


def analyze_code(code: str, filename: str = "uploaded.py") -> dict[str, Any]:
    loc = count_loc(code)
    comments = count_comments(code)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return empty_analysis(filename, loc, comments, str(exc))

    visitor = MetricVisitor()
    visitor.visit(tree)
    visitor.variables.total = len(visitor.variables.names)
    visitor.variables.unused = len(
        {
            name
            for name in visitor.variables.assigned
            if name not in visitor.variables.used and not name.startswith("_")
        }
    )

    function_total = len(visitor.functions)
    long_methods = [fn for fn in visitor.functions if "long_method" in fn["flags"]]
    parameter_heavy = [fn for fn in visitor.functions if "too_many_parameters" in fn["flags"]]
    refactoring = build_refactoring_recommendations(long_methods, parameter_heavy, visitor.complexity)
    quality_score = code_quality_score(loc, visitor.complexity, visitor.variables.unused, function_total)
    maintainability = maintainability_score(loc, visitor.complexity, comments, visitor.variables.unused)
    performance_score = max(0, 100 - len(visitor.performance_patterns) * 10 - visitor.nested_loops * 5)
    memory_score = max(0, 100 - len(visitor.memory_patterns) * 12)
    technical_debt = min(100, (100 - maintainability) * 0.5 + len(refactoring) * 8 + len(visitor.performance_patterns) * 4)
    security_score = estimate_security_score(tree)
    documentation_score = min(100, comments * 3 + docstring_score(tree))
    health = calculate_health_score(
        maintainability=maintainability,
        security=security_score,
        performance=performance_score,
        code_quality=quality_score,
        documentation=documentation_score,
    )
    recommendations = build_optimization_recommendations(
        visitor.memory_patterns,
        visitor.performance_patterns,
        refactoring,
        memory_score,
        performance_score,
    )

    return {
        "repository_id": filename,
        "filename": filename,
        "metrics": {
            "loc": loc,
            "classes": visitor.classes,
            "functions": function_total,
            "variables": visitor.variables.total,
            "imports": visitor.imports,
            "comment_percentage": round((comments / max(1, loc + comments)) * 100, 2),
            "cyclomatic_complexity": visitor.complexity,
            "maintainability_score": round(maintainability, 2),
            "technical_debt_score": round(technical_debt, 2),
            "code_quality_score": round(quality_score, 2),
        },
        "variables": {
            "total": visitor.variables.total,
            "global": visitor.variables.global_count,
            "local": visitor.variables.local_count,
            "unused": visitor.variables.unused,
            "unused_names": sorted(
                name for name in visitor.variables.assigned if name not in visitor.variables.used and not name.startswith("_")
            ),
        },
        "functions": {
            "total": function_total,
            "long_methods": long_methods,
            "too_many_parameters": parameter_heavy,
            "refactoring_opportunities": refactoring,
        },
        "memory": {
            "score": memory_score,
            "patterns": visitor.memory_patterns,
            "recommendations": [recommendation_for_pattern(pattern) for pattern in visitor.memory_patterns],
        },
        "performance": {
            "score": performance_score,
            "nested_loops": visitor.nested_loops,
            "patterns": visitor.performance_patterns,
            "recommendations": [recommendation_for_pattern(pattern) for pattern in visitor.performance_patterns],
        },
        "health": health,
        "recommendations": recommendations,
        "syntax_error": None,
    }


def empty_analysis(filename: str, loc: int, comments: int, error: str) -> dict[str, Any]:
    return {
        "repository_id": filename,
        "filename": filename,
        "metrics": {
            "loc": loc,
            "classes": 0,
            "functions": 0,
            "variables": 0,
            "imports": 0,
            "comment_percentage": round((comments / max(1, loc + comments)) * 100, 2),
            "cyclomatic_complexity": 0,
            "maintainability_score": 0,
            "technical_debt_score": 100,
            "code_quality_score": 0,
        },
        "variables": {"total": 0, "global": 0, "local": 0, "unused": 0, "unused_names": []},
        "functions": {"total": 0, "long_methods": [], "too_many_parameters": [], "refactoring_opportunities": []},
        "memory": {"score": 0, "patterns": [], "recommendations": []},
        "performance": {"score": 0, "nested_loops": 0, "patterns": [], "recommendations": []},
        "health": calculate_health_score(0, 70, 0, 0, 0),
        "recommendations": [{"category": "syntax", "message": f"Fix syntax error before deeper analysis: {error}", "priority": "high"}],
        "syntax_error": error,
    }


def calculate_health_score(
    maintainability: float,
    security: float,
    performance: float,
    code_quality: float,
    documentation: float,
) -> dict[str, Any]:
    score = (
        maintainability * 0.30
        + security * 0.20
        + performance * 0.20
        + code_quality * 0.15
        + documentation * 0.15
    )
    if score >= 85:
        label = "Excellent"
    elif score >= 70:
        label = "Good"
    elif score >= 50:
        label = "Average"
    else:
        label = "Poor"
    return {
        "score": round(score, 2),
        "rating": label,
        "components": {
            "maintainability": round(maintainability, 2),
            "security": round(security, 2),
            "performance": round(performance, 2),
            "code_quality": round(code_quality, 2),
            "documentation": round(documentation, 2),
        },
    }


def count_loc(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.strip() and not line.strip().startswith("#"))


def count_comments(code: str) -> int:
    count = 0
    try:
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type == tokenize.COMMENT:
                count += 1
    except tokenize.TokenError:
        return sum(1 for line in code.splitlines() if line.strip().startswith("#"))
    return count


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def issue(kind: str, line: int, message: str) -> dict[str, Any]:
    return {"type": kind, "line": line, "message": message}


def code_quality_score(loc: int, complexity: int, unused_variables: int, functions: int) -> float:
    score = 100 - max(0, complexity - 10) * 2 - unused_variables * 3
    if functions and loc / functions > LONG_METHOD_LINES:
        score -= 10
    return max(0, min(100, score))


def maintainability_score(loc: int, complexity: int, comments: int, unused_variables: int) -> float:
    score = 100 - min(35, loc / 20) - min(35, complexity * 1.5) - min(20, unused_variables * 2)
    if comments:
        score += min(10, comments)
    return max(0, min(100, score))


def docstring_score(tree: ast.AST) -> float:
    documented = 0
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            total += 1
            if ast.get_docstring(node):
                documented += 1
    return 100 if total == 0 else (documented / total) * 100


def estimate_security_score(tree: ast.AST) -> float:
    risky_calls = {"eval", "exec", "pickle.loads", "subprocess.run", "subprocess.Popen", "os.system"}
    score = 100
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and call_name(node.func) in risky_calls:
            score -= 15
    return max(0, score)


def build_refactoring_recommendations(long_methods: list[dict[str, Any]], parameter_heavy: list[dict[str, Any]], complexity: int) -> list[str]:
    recommendations = []
    for fn in long_methods:
        recommendations.append(f"Split `{fn['name']}` into smaller functions; it spans {fn['lines']} lines.")
    for fn in parameter_heavy:
        recommendations.append(f"Reduce parameters in `{fn['name']}` or introduce a request/config object.")
    if complexity > 15:
        recommendations.append("Reduce cyclomatic complexity with guard clauses, strategy objects, or smaller helpers.")
    return recommendations


def recommendation_for_pattern(pattern: dict[str, Any]) -> str:
    mapping = {
        "nested_loop": "Consider indexing, hashing, batching, or precomputing lookups to avoid quadratic work.",
        "nested_comprehension": "Replace nested comprehensions with clearer staged processing for large inputs.",
        "repeated_io_call": "Move database/API calls outside loops or batch the requests.",
        "blocking_operation": "Use async/non-blocking alternatives or move blocking work to a worker.",
        "duplicate_computation": "Cache repeated expensive expressions in a local variable.",
        "inefficient_api_usage": "Prefer streaming, pagination, or targeted queries over broad materialization APIs.",
        "large_read": "Stream data in chunks instead of reading the entire file at once.",
        "large_result_fetch": "Use cursor iteration, pagination, or bounded fetches instead of loading every row.",
        "eager_collection_copy": "Avoid copying large collections unless mutation or materialization is required.",
        "repeated_allocation": "Reuse objects or allocate collections outside hot loops where possible.",
        "list_comprehension": "Use generator expressions for large one-pass transformations.",
        "set_comprehension": "Use lazy iteration when uniqueness is not required immediately.",
        "dict_comprehension": "Build dictionaries incrementally only when all entries are needed.",
    }
    return mapping.get(pattern["type"], pattern["message"])


def build_optimization_recommendations(
    memory_patterns: list[dict[str, Any]],
    performance_patterns: list[dict[str, Any]],
    refactoring: list[str],
    memory_score: float,
    performance_score: float,
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    priority = "high" if memory_score < 70 else "medium"
    for pattern in memory_patterns[:8]:
        recommendations.append({"category": "memory", "message": recommendation_for_pattern(pattern), "priority": priority})
    priority = "high" if performance_score < 70 else "medium"
    for pattern in performance_patterns[:8]:
        recommendations.append({"category": "performance", "message": recommendation_for_pattern(pattern), "priority": priority})
    for message in refactoring[:8]:
        recommendations.append({"category": "refactoring", "message": message, "priority": "medium"})
    if not recommendations:
        recommendations.append({"category": "quality", "message": "No high-impact optimization issues detected.", "priority": "low"})
    return recommendations
