# Code Raptor Project Guide

This document explains Code Raptor from the root level, so you can work on the project with understanding instead of only running commands blindly.

## 1. What This Application Does

Code Raptor is a microservice-based code review application.

Users can:

- register and login
- paste or upload Python code
- upload an image that contains code
- extract code from the image using Azure AI
- run Python code safely through a separate execution service
- ask Azure AI to review the code
- apply the fixed code
- view code health metrics such as variables, functions, memory safety, speed score, cleanup needed, and overall health
- save review history
- download a review report

The application is split into small services. Each service has one main job.

## 2. Root-Level Folder Structure

```text
AI-Codereviewer/
├── auth_service/          # Handles user register/login
├── execution_service/     # Runs submitted Python code
├── ai_service/            # Talks to Azure AI Foundry / Azure OpenAI
├── review_service/        # Stores reviews and code analysis metrics
├── frontend/              # Streamlit web UI
├── tests/                 # Unit tests for analyzers
├── docker-compose.yml     # Runs all services together
├── .env                   # Real local secrets/config, not committed
├── .env.example           # Example root env file
├── CODE_RAPTOR.md         # This guide
└── coderaptor.py          # Older standalone Streamlit version
```

The main application uses the microservices and `frontend/app.py`. The older `coderaptor.py` file is a standalone version and is not used by Docker Compose.

## 3. Microservices Overview

| Service | Folder | Port | Main Responsibility |
|---|---|---:|---|
| Frontend | `frontend/` | `8501` | User interface built with Streamlit |
| Auth Service | `auth_service/` | `8001` | User registration and login |
| Execution Service | `execution_service/` | `8002` | Runs Python code and returns output |
| AI Service | `ai_service/` | `8003` | Sends review/extraction requests to Azure OpenAI |
| Review Service | `review_service/` | `8004` | Saves review history and stores metrics |
| PostgreSQL | Docker image | `5432` | Shared database for auth and review data |

## 4. High-Level Architecture

```text
Browser
  |
  v
Frontend: Streamlit app
  |
  |-- login/register -------------> Auth Service --------> PostgreSQL
  |
  |-- run code -------------------> Execution Service
  |
  |-- AI review / image extract --> AI Service ----------> Azure OpenAI
  |
  |-- save/load review -----------> Review Service ------> PostgreSQL
                                      |
                                      v
                              AST Code Analyzer
```

The frontend never talks directly to the database or Azure OpenAI. It only calls backend services.

## 5. Docker Compose Architecture

`docker-compose.yml` starts all services together.

Important ports:

```text
Frontend:          http://localhost:8501
Auth Service:      http://localhost:8001
Execution Service: http://localhost:8002
AI Service:        http://localhost:8003
Review Service:    http://localhost:8004
PostgreSQL:        localhost:5432
```

The frontend uses internal Docker service names:

```env
AUTH_SERVICE_URL=http://auth-service:8001
EXECUTION_SERVICE_URL=http://execution-service:8002
AI_SERVICE_URL=http://ai-service:8003
REVIEW_SERVICE_URL=http://review-service:8004
```

Inside Docker, services talk to each other by service name, not by `localhost`.

## 6. Environment Configuration

The root `.env` is used by Docker Compose.

Required root variables:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_API_VERSION=2025-01-01-preview

POSTGRES_DB=coderaptor
POSTGRES_USER=coderaptor
POSTGRES_PASSWORD=coderaptor
```

Each service also has a `.env.example` file for standalone runs:

```text
auth_service/.env.example
execution_service/.env.example
ai_service/.env.example
review_service/.env.example
frontend/.env.example
```

For Docker Compose, use the root `.env`.

## 7. Frontend Service

Folder:

```text
frontend/
```

Main file:

```text
frontend/app.py
```

Technology:

```text
Streamlit
```

Responsibilities:

- shows login/register page
- shows code editor
- handles file/image upload
- calls AI service for review and image extraction
- calls execution service to run code
- calls review service to save and load reviews
- displays code health dashboard
- displays fixed code before/after comparison
- downloads Markdown review report

Important frontend functions:

| Function | Purpose |
|---|---|
| `authenticate()` | Calls auth service login API |
| `register_user()` | Calls auth service register API |
| `review_code()` | Calls AI service `/review` |
| `run_code()` | Calls execution service `/run` |
| `save_review()` | Calls review service to save code/review |
| `load_user_reviews()` | Loads saved reviews from review service |
| `render_analysis_cards()` | Shows code health dashboard |
| `build_review_report()` | Creates downloadable report |

Frontend pages:

- Login/Register
- Code Review
- Code Health
- About

## 8. Auth Service

Folder:

```text
auth_service/
```

Main file:

```text
auth_service/main.py
```

Port:

```text
8001
```

Responsibilities:

- register new users
- login users
- store user credentials in PostgreSQL

Database table:

```sql
users (
    username TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
```

Important APIs:

```text
POST /register
POST /login
GET  /health
GET  /ready
GET  /live
GET  /metrics
```

Register request:

```json
{
  "username": "thanu",
  "email": "thanu@example.com",
  "password": "password123"
}
```

Login request:

```json
{
  "email": "thanu@example.com",
  "password": "password123"
}
```

Note: Passwords are hashed before storage. This project uses simple hashing for learning/demo purposes.

## 9. Execution Service

Folder:

```text
execution_service/
```

Main file:

```text
execution_service/main.py
```

Port:

```text
8002
```

Responsibilities:

- receives Python code
- writes it to a temporary `.py` file
- runs it using `python3`
- captures output and errors
- deletes the temporary file

Important API:

```text
POST /run
```

Request:

```json
{
  "code": "print('Hello')",
  "tab_id": "test"
}
```

Response:

```json
{
  "output": "Hello\n"
}
```

Safety behavior:

- execution timeout is 30 seconds
- temporary file is removed after execution
- stdout and stderr are both returned
- if code prints nothing, the service returns a friendly success message

## 10. AI Service

Folder:

```text
ai_service/
```

Main file:

```text
ai_service/main.py
```

Port:

```text
8003
```

Responsibilities:

- sends code review requests to Azure OpenAI
- sends image extraction requests to Azure OpenAI vision-capable deployment
- extracts valid Python fixed code from AI response
- handles Azure errors in a user-friendly way

Provider:

```text
Azure AI Foundry / Azure OpenAI
```

Required env:

```env
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=
```

Important APIs:

```text
POST /review
POST /extract
GET  /health
GET  /ready
GET  /live
GET  /metrics
```

Review request:

```json
{
  "code": "def add(a,b): return a+b"
}
```

Review response:

```json
{
  "review_output": "AI review text...",
  "fixed_code": "def add(a, b):\n    return a + b"
}
```

How Azure OpenAI is called:

```text
POST {AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version={AZURE_OPENAI_API_VERSION}
```

The app uses the deployment name, not just the model name. If your deployment is named `gpt-4.1-mini`, then:

```env
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
```

## 11. Review Service

Folder:

```text
review_service/
```

Main file:

```text
review_service/main.py
```

Analyzer:

```text
review_service/analyzers/code_metrics.py
```

Port:

```text
8004
```

Responsibilities:

- save review history
- load review history
- delete reviews
- analyze code using Python AST
- store code metrics in PostgreSQL
- expose dashboard APIs

Important APIs:

```text
GET    /reviews/{username}
POST   /reviews/{username}
DELETE /reviews/{tab_id}

GET /api/metrics/{repository_id}
GET /api/memory/{repository_id}
GET /api/performance/{repository_id}
GET /api/health/{repository_id}
GET /api/recommendations/{repository_id}
GET /api/analysis/{repository_id}
```

Monitoring APIs:

```text
GET /health
GET /ready
GET /live
GET /metrics
```

## 12. Database Design

PostgreSQL is used by:

- Auth Service
- Review Service

Main tables:

```text
users
reviews
repository_metrics
memory_analysis
performance_analysis
health_scores
optimization_recommendations
```

Migration file:

```text
review_service/migrations/001_repository_analysis.sql
```

The app also creates tables automatically when services start.

## 13. Code Analysis Engine

File:

```text
review_service/analyzers/code_metrics.py
```

The analyzer uses Python `ast`.

It calculates:

- lines of code
- number of classes
- number of functions
- number of variables
- global variables
- local variables
- unused variables
- imports
- comment percentage
- logic complexity
- maintainability score
- cleanup needed score
- code quality score
- memory safety score
- speed score
- overall health score

It detects:

- long methods
- too many function parameters
- nested loops
- repeated database/API calls
- blocking operations
- duplicate computations
- large reads
- repeated allocations
- large result fetching

Health score formula:

```text
Health Score =
30% Maintainability
20% Security
20% Performance
15% Code Quality
15% Documentation
```

Ratings:

```text
85-100 = Excellent
70-84  = Good
50-69  = Average
0-49   = Poor
```

## 14. Full Application Workflow

### Workflow 1: User Login

```text
User enters email/password
  -> Frontend calls Auth Service /login
  -> Auth Service checks PostgreSQL users table
  -> Auth Service returns username
  -> Frontend loads saved review history
```

### Workflow 2: Code Review

```text
User pastes code
  -> Frontend calls AI Service /review
  -> AI Service sends prompt to Azure OpenAI
  -> Azure returns review text and corrected code
  -> AI Service extracts valid Python fixed code
  -> Frontend saves review through Review Service
  -> Review Service runs local analyzer
  -> Review Service stores metrics in PostgreSQL
  -> Frontend displays review and code health
```

### Workflow 3: Apply Fixed Code

```text
User clicks Apply & Run Fixed Code
  -> Frontend validates fixed code
  -> Frontend replaces editor code
  -> Frontend calls Execution Service /run
  -> Execution Service runs code
  -> Frontend displays output
  -> Frontend saves updated review
```

### Workflow 4: Run Code

```text
User clicks Run Code
  -> Frontend calls Execution Service /run
  -> Execution Service writes code to temp file
  -> Execution Service runs python3
  -> Execution Service returns stdout/stderr
  -> Frontend displays output
```

### Workflow 5: Upload Image

```text
User uploads image
  -> Frontend sends image to AI Service /extract
  -> AI Service converts image to base64
  -> AI Service sends image to Azure OpenAI
  -> Azure returns extracted code
  -> Frontend validates Python syntax
  -> Frontend places code in editor
```

### Workflow 6: Code Health Dashboard

```text
Review is saved
  -> Review Service analyzes code
  -> Metrics are saved in PostgreSQL
  -> Frontend calls /api/analysis/{review_id}
  -> Frontend displays score cards and suggestions
```

## 15. How To Run The Project

From the root folder:

```bash
docker compose down
docker compose up --build --force-recreate
```

Open:

```text
http://localhost:8501
```

## 16. How To Check Each Service

Auth:

```bash
curl http://localhost:8001/health
curl http://localhost:8001/ready
```

Execution:

```bash
curl http://localhost:8002/health
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{"code":"print(\"Hello\")","tab_id":"test"}'
```

AI:

```bash
curl http://localhost:8003/health
curl http://localhost:8003/ready
curl -X POST http://localhost:8003/review \
  -H "Content-Type: application/json" \
  -d '{"code":"def add(a,b): return a+b"}'
```

Review:

```bash
curl http://localhost:8004/health
curl http://localhost:8004/ready
```

Frontend:

```text
http://localhost:8501
```

## 17. How To Debug

View all logs:

```bash
docker compose logs
```

View one service:

```bash
docker compose logs ai-service
docker compose logs review-service
docker compose logs auth-service
docker compose logs execution-service
docker compose logs frontend
```

Rebuild one service:

```bash
docker compose up --build --force-recreate ai-service
```

Enter a container:

```bash
docker compose exec ai-service sh
```

Check database:

```bash
docker compose exec postgres psql -U coderaptor -d coderaptor
```

List tables:

```sql
\dt
```

## 18. Common Issues

### AI service says deployment not found

Check:

```env
AZURE_OPENAI_DEPLOYMENT=
```

It must match the deployment name in Azure AI Foundry exactly.

### AI service says unauthorized

Check:

```env
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
```

Make sure the key belongs to the same Azure OpenAI resource as the endpoint.

### AI service says unsupported API version

Try:

```env
AZURE_OPENAI_API_VERSION=2024-10-21
```

Then restart Docker.

### Frontend cannot reach services

Inside Docker Compose, frontend must use:

```text
http://auth-service:8001
http://execution-service:8002
http://ai-service:8003
http://review-service:8004
```

Outside Docker, use:

```text
http://localhost:8001
http://localhost:8002
http://localhost:8003
http://localhost:8004
```

### Code review works but fixed code is empty

This can happen if Azure returns explanation but no valid Python code block. The app will still show the review and local code health metrics.

## 19. Testing

Unit tests are in:

```text
tests/test_analyzers.py
```

They test:

- variable analyzer
- complexity analyzer
- health score calculator
- performance analyzer
- memory analyzer

Run with pytest if installed:

```bash
python -m pytest tests
```

If pytest is not installed, the analyzer functions can still be checked manually.

## 20. Important Files To Study First

Start with these files in this order:

```text
docker-compose.yml
frontend/app.py
ai_service/main.py
review_service/main.py
review_service/analyzers/code_metrics.py
auth_service/main.py
execution_service/main.py
```

This order teaches you:

1. how services run together
2. how the UI calls backend services
3. how Azure AI is called
4. how reviews and metrics are saved
5. how code analysis works
6. how login works
7. how code execution works

## 21. Mental Model

Think of Code Raptor like this:

```text
Frontend = user control panel
Auth Service = identity gate
AI Service = Azure AI adapter
Execution Service = Python runner
Review Service = history + code health brain
PostgreSQL = memory of the system
```

The frontend coordinates everything, but each backend service owns one responsibility.

That is the core architecture of this project.
