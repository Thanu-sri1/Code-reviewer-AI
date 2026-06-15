# Review Service Analysis API Contracts

All endpoints use `repositoryId` as the saved review id.

## `GET /api/metrics/{repositoryId}`

Returns AST-based repository metrics and embedded variable/function analysis.

```json
{
  "repository_id": "review-id",
  "filename": "review-id",
  "loc": 42,
  "classes": 1,
  "functions": 4,
  "variables": 12,
  "imports": 3,
  "comment_percentage": 8.33,
  "cyclomatic_complexity": 9,
  "maintainability_score": 78.5,
  "technical_debt_score": 18.2,
  "code_quality_score": 91,
  "variable_analysis": {
    "total": 12,
    "global": 2,
    "local": 10,
    "unused": 1,
    "unused_names": ["temp"]
  },
  "function_analysis": {
    "total": 4,
    "long_methods": [],
    "too_many_parameters": [],
    "refactoring_opportunities": []
  }
}
```

## `GET /api/memory/{repositoryId}`

Returns memory score, detected allocation-heavy patterns, and recommendations.

## `GET /api/performance/{repositoryId}`

Returns performance score, nested loop count, detected performance patterns, and recommendations.

## `GET /api/health/{repositoryId}`

Returns weighted health score and rating.

Weights: 30% maintainability, 20% security, 20% performance, 15% code quality, 15% documentation.

## `GET /api/recommendations/{repositoryId}`

Returns flattened optimization recommendations with `category`, `message`, and `priority`.

## `GET /api/analysis/{repositoryId}`

Returns a dashboard-friendly bundle containing metrics, memory, performance, health, and recommendations.
