CREATE TABLE IF NOT EXISTS repository_metrics (
    repository_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
    filename TEXT,
    loc INTEGER NOT NULL DEFAULT 0,
    classes INTEGER NOT NULL DEFAULT 0,
    functions INTEGER NOT NULL DEFAULT 0,
    variables INTEGER NOT NULL DEFAULT 0,
    imports INTEGER NOT NULL DEFAULT 0,
    comment_percentage NUMERIC NOT NULL DEFAULT 0,
    cyclomatic_complexity INTEGER NOT NULL DEFAULT 0,
    maintainability_score NUMERIC NOT NULL DEFAULT 0,
    technical_debt_score NUMERIC NOT NULL DEFAULT 0,
    code_quality_score NUMERIC NOT NULL DEFAULT 0,
    variable_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    function_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE reviews
ADD COLUMN IF NOT EXISTS fixed_code_language TEXT NOT NULL DEFAULT 'python';

CREATE TABLE IF NOT EXISTS memory_analysis (
    repository_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
    score NUMERIC NOT NULL DEFAULT 0,
    patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS performance_analysis (
    repository_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
    score NUMERIC NOT NULL DEFAULT 0,
    nested_loops INTEGER NOT NULL DEFAULT 0,
    patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS health_scores (
    repository_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
    score NUMERIC NOT NULL DEFAULT 0,
    rating TEXT NOT NULL,
    components JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS optimization_recommendations (
    id SERIAL PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
