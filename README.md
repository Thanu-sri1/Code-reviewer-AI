# Code Raptor

Code Raptor is a microservice-based AI code review platform. It provides a Streamlit UI for code review, code execution, repository analysis, review history, and code health dashboards backed by FastAPI services, PostgreSQL, and Azure OpenAI / Azure AI Foundry.

For a deeper architecture walkthrough, see [CODE_RAPTOR.md](CODE_RAPTOR.md).

## Features

- User registration and login
- Paste, edit, upload, and review source code
- AI review feedback with corrected-code extraction
- Image-to-code extraction through Azure OpenAI vision-capable deployments
- GitHub repository review with asynchronous job status and downloadable reports
- Code execution for Python, Java, JavaScript, and YAML validation
- Saved review history per user
- Code health metrics for maintainability, security, performance, code quality, and documentation
- Memory, speed, cleanup, variable, and function analysis
- Docker Compose local development setup
- AKS manifests with Azure Key Vault integration

## Architecture

```text
Browser
  |
  v
Frontend: Streamlit
  |
  |-- register/login ------------> Auth Service -------> PostgreSQL
  |-- run code ------------------> Execution Service
  |-- AI review / extraction ----> AI Service ---------> Azure OpenAI
  |-- history / repo review -----> Review Service -----> PostgreSQL
                                      |
                                      v
                              Local code analyzers
```

## Services

| Service | Folder | Local Port | Purpose |
|---|---|---:|---|
| Frontend | `frontend/` | `8501` | Streamlit web UI |
| Auth Service | `auth_service/` | `8001` | User registration and login |
| Execution Service | `execution_service/` | `8002` | Code execution and YAML validation |
| AI Service | `ai_service/` | `8003` | Azure OpenAI review and extraction |
| Review Service | `review_service/` | `8004` | Review history, repository review, and metrics |
| PostgreSQL | Docker image | `5432` | Database for users, reviews, jobs, and metrics |

## Prerequisites

- Docker and Docker Compose
- Azure OpenAI / Azure AI Foundry resource
- Azure OpenAI deployment name for the model used by the app
- Optional local tools for non-Docker development: Python, Java/JDK, Node.js, PostgreSQL

## Local Setup

Create a root `.env` from the example:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Update the Azure values in `.env`:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_KEY=your-azure-openai-key
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_API_VERSION=2025-01-01-preview

POSTGRES_DB=coderaptor
POSTGRES_USER=coderaptor
POSTGRES_PASSWORD=coderaptor
```

Start the full stack:

```bash
docker compose up --build
```

Open the app:

```text
http://localhost:8501
```

To recreate containers from scratch:

```bash
docker compose down
docker compose up --build --force-recreate
```

## Configuration Notes

- The root `.env` is used by Docker Compose.
- `frontend/.env.example` is only needed when running the frontend outside Docker.
- In Docker, the frontend calls services by container name, such as `http://ai-service:8003`.
- Outside Docker, use localhost service URLs, such as `http://localhost:8003`.
- Do not commit real `.env` files or secrets.

## Health Checks

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
```

Readiness and liveness endpoints are also available:

```bash
curl http://localhost:8001/ready
curl http://localhost:8002/ready
curl http://localhost:8003/ready
curl http://localhost:8004/ready
curl http://localhost:8001/live
curl http://localhost:8002/live
curl http://localhost:8003/live
curl http://localhost:8004/live
```

## Useful API Examples

Run Python:

```bash
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{"code":"print(\"Hello Python\")","tab_id":"test","language":"python"}'
```

Run JavaScript:

```bash
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{"code":"console.log(\"Hello JavaScript\")","tab_id":"test","language":"javascript"}'
```

Validate YAML:

```bash
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{"code":"apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod\nspec:\n  containers:\n    - name: app\n      image: nginx","tab_id":"test","language":"yaml"}'
```

Request an AI code review:

```bash
curl -X POST http://localhost:8003/review \
  -H "Content-Type: application/json" \
  -d '{"code":"def add(a,b): return a+b","mode":"Full Repository Review"}'
```

Start a repository review:

```bash
curl -X POST http://localhost:8004/review/repository \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","repository_url":"https://github.com/org/repo","mode":"Full Repository Review"}'
```

Check a repository review job:

```bash
curl http://localhost:8004/review/status/<job_id>
curl http://localhost:8004/review/result/<job_id>
```

## Review Service Analysis APIs

Saved reviews expose dashboard-friendly analysis endpoints:

```text
GET /api/metrics/{repository_id}
GET /api/memory/{repository_id}
GET /api/performance/{repository_id}
GET /api/health/{repository_id}
GET /api/recommendations/{repository_id}
GET /api/analysis/{repository_id}
```

See [review_service/API_CONTRACTS.md](review_service/API_CONTRACTS.md) for response examples.

## Testing

Run unit tests:

```bash
python -m pytest tests
```

Run a Python compile check:

```bash
python -m compileall auth_service review_service ai_service execution_service frontend tests
```

## Troubleshooting

View all service logs:

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

Open PostgreSQL:

```bash
docker compose exec postgres psql -U coderaptor -d coderaptor
```

Common checks:

- If the AI service returns authentication errors, confirm `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` belong to the same Azure resource.
- If the AI service says the deployment was not found, confirm `AZURE_OPENAI_DEPLOYMENT` matches the Azure deployment name exactly.
- If the frontend cannot reach services outside Docker, use `http://localhost:<port>` URLs.
- If the frontend cannot reach services inside Docker, use Compose service names such as `http://review-service:8004`.

## AKS Deployment

Kubernetes manifests are in [k8s](k8s).

The AKS deployment uses Azure Key Vault through the Secrets Store CSI driver. Before deploying, replace manifest placeholders such as:

```text
<ACR_LOGIN_SERVER>
<AZURE_KEY_VAULT_NAME>
<AZURE_TENANT_ID>
<USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID>
```

Then deploy:

```bash
kubectl apply -f k8s/
```

For the full AKS and Key Vault workflow, see [k8s/README_AKS_KEYVAULT.md](k8s/README_AKS_KEYVAULT.md).

## Important Files

```text
docker-compose.yml
frontend/app.py
auth_service/main.py
execution_service/main.py
ai_service/main.py
review_service/main.py
review_service/repository_review.py
review_service/analyzers/code_metrics.py
review_service/API_CONTRACTS.md
k8s/README_AKS_KEYVAULT.md
CODE_RAPTOR.md
```

## Legacy Entry Point

`coderaptor.py` is an older standalone Streamlit version. The active application entry point for Docker Compose is `frontend/app.py`.
