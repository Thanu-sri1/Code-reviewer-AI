# Code Raptor

Code Raptor is a microservice-based AI code review application. It lets users paste or upload code, run supported languages, get Azure AI review feedback, apply fixed code, and view code health metrics.

For the full architecture explanation, read:

```text
CODE_RAPTOR.md
```

## Features

- User registration and login
- Code editor with review history
- Azure OpenAI / Azure AI Foundry based code review
- Image-to-code extraction
- Code execution for:
  - Python
  - Java
  - JavaScript
  - YAML validation
- Code health dashboard
- Variable, function, memory, speed, and cleanup analysis
- Downloadable review report
- Docker Compose local setup
- AKS deployment manifests with Azure Key Vault integration

## Microservices

| Service | Folder | Port | Purpose |
|---|---|---:|---|
| Frontend | `frontend/` | `8501` | Streamlit UI |
| Auth Service | `auth_service/` | `8001` | Register/login |
| Execution Service | `execution_service/` | `8002` | Runs code and validates YAML |
| AI Service | `ai_service/` | `8003` | Azure OpenAI review/extraction |
| Review Service | `review_service/` | `8004` | Review history and metrics |
| PostgreSQL | Docker image | `5432` | Database |

## Local Setup

Create a root `.env` file:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_API_VERSION=2025-01-01-preview

POSTGRES_DB=coderaptor
POSTGRES_USER=coderaptor
POSTGRES_PASSWORD=coderaptor
```

Start the app:

```bash
docker compose down
docker compose up --build --force-recreate
```

Open:

```text
http://localhost:8501
```

## Health Checks

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
```

AI readiness:

```bash
curl http://localhost:8003/ready
```

## Test Execution Service

Python:

```bash
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{"code":"print(\"Hello Python\")","tab_id":"test","language":"python"}'
```

Java:

```bash
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{"code":"public class Main { public static void main(String[] args) { System.out.println(\"Hello Java\"); } }","tab_id":"test","language":"java"}'
```

YAML:

```bash
curl -X POST http://localhost:8002/run \
  -H "Content-Type: application/json" \
  -d '{"code":"apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod\nspec:\n  containers:\n    - name: app\n      image: nginx","tab_id":"test","language":"yaml"}'
```

## Test AI Review

```bash
curl -X POST http://localhost:8003/review \
  -H "Content-Type: application/json" \
  -d '{"code":"def add(a,b): return a+b"}'
```

## Run Tests

If `pytest` is installed:

```bash
python -m pytest tests
```

Compile check:

```bash
python3 -m compileall auth_service review_service ai_service execution_service frontend tests
```

## AKS Deployment

Kubernetes manifests are in:

```text
k8s/
```

The AKS setup uses Azure Key Vault through the Secrets Store CSI driver.

Read:

```text
k8s/README_AKS_KEYVAULT.md
```

Before deploying, replace placeholders in the manifests:

```text
<ACR_LOGIN_SERVER>
<AZURE_KEY_VAULT_NAME>
<AZURE_TENANT_ID>
<USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID>
```

Deploy:

```bash
kubectl apply -k k8s/
```

## Important Files

```text
docker-compose.yml
frontend/app.py
ai_service/main.py
execution_service/main.py
review_service/main.py
review_service/analyzers/code_metrics.py
auth_service/main.py
CODE_RAPTOR.md
k8s/README_AKS_KEYVAULT.md
```

## Notes

- Do not commit `.env`.
- Use `.env.example` files as templates only.
- The local database uses Docker volume `postgres_data`.
- The AKS deployment uses Key Vault for secrets.
