# AKS Deployment With Azure Key Vault

This folder deploys Code Raptor to AKS and reads secrets from Azure Key Vault through the Secrets Store CSI driver.

## What Key Vault Stores

Create these Key Vault secrets:

| Key Vault Secret Name | Mounted File Name | Used By |
|---|---|---|
| `azure-openai-endpoint` | `AZURE_OPENAI_ENDPOINT` | AI service |
| `azure-openai-api-key` | `AZURE_OPENAI_API_KEY` | AI service |
| `azure-openai-deployment` | `AZURE_OPENAI_DEPLOYMENT` | AI service |
| `azure-openai-api-version` | `AZURE_OPENAI_API_VERSION` | AI service |
| `database-url` | `DATABASE_URL` | Auth and review services |
| `postgres-password` | `POSTGRES_PASSWORD` | PostgreSQL |

Example `database-url` value:

```text
postgresql://coderaptor:<POSTGRES_PASSWORD>@postgres:5432/coderaptor
```

## 1. Enable Key Vault CSI Driver On AKS

```bash
az aks enable-addons \
  --resource-group <RESOURCE_GROUP> \
  --name <AKS_CLUSTER_NAME> \
  --addons azure-keyvault-secrets-provider
```

Get the addon identity client id:

```bash
az aks show \
  --resource-group <RESOURCE_GROUP> \
  --name <AKS_CLUSTER_NAME> \
  --query addonProfiles.azureKeyvaultSecretsProvider.identity.clientId \
  -o tsv
```

Put that value into:

```text
k8s/02-secretproviderclass.yaml
```

Replace:

```text
<USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID>
```

## 2. Allow AKS Identity To Read Key Vault

```bash
az keyvault set-policy \
  --name <AZURE_KEY_VAULT_NAME> \
  --secret-permissions get list \
  --spn <USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID>
```

If your Key Vault uses Azure RBAC instead of access policies, assign:

```text
Key Vault Secrets User
```

to the managed identity at the Key Vault scope.

## 3. Create Key Vault Secrets

```bash
az keyvault secret set --vault-name <AZURE_KEY_VAULT_NAME> --name azure-openai-endpoint --value "https://ai-codereviewer-resource.openai.azure.com/"
az keyvault secret set --vault-name <AZURE_KEY_VAULT_NAME> --name azure-openai-api-key --value "<AZURE_OPENAI_API_KEY>"
az keyvault secret set --vault-name <AZURE_KEY_VAULT_NAME> --name azure-openai-deployment --value "gpt-4.1-mini"
az keyvault secret set --vault-name <AZURE_KEY_VAULT_NAME> --name azure-openai-api-version --value "2025-01-01-preview"
az keyvault secret set --vault-name <AZURE_KEY_VAULT_NAME> --name postgres-password --value "<POSTGRES_PASSWORD>"
az keyvault secret set --vault-name <AZURE_KEY_VAULT_NAME> --name database-url --value "postgresql://coderaptor:<POSTGRES_PASSWORD>@postgres:5432/coderaptor"
```

## 4. Update Manifests

In `k8s/02-secretproviderclass.yaml`, replace:

```text
<AZURE_KEY_VAULT_NAME>
<AZURE_TENANT_ID>
<USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID>
```

In deployment files, replace:

```text
<ACR_LOGIN_SERVER>
```

Example:

```text
myregistry.azurecr.io
```

## 5. Build And Push Images

```bash
ACR=<ACR_LOGIN_SERVER>

docker build -t $ACR/auth-service:latest ./auth_service
docker build -t $ACR/execution-service:latest ./execution_service
docker build -t $ACR/ai-service:latest ./ai_service
docker build -t $ACR/review-service:latest ./review_service
docker build -t $ACR/frontend:latest ./frontend

docker push $ACR/auth-service:latest
docker push $ACR/execution-service:latest
docker push $ACR/ai-service:latest
docker push $ACR/review-service:latest
docker push $ACR/frontend:latest
```

Make sure AKS can pull from ACR:

```bash
az aks update \
  --resource-group <RESOURCE_GROUP> \
  --name <AKS_CLUSTER_NAME> \
  --attach-acr <ACR_NAME>
```

## 6. Deploy To AKS

```bash
kubectl apply -k k8s/
```

Check pods:

```bash
kubectl get pods -n coderaptor
```

Check services:

```bash
kubectl get svc -n coderaptor
```

Get frontend public IP:

```bash
kubectl get svc frontend -n coderaptor
```

## 7. Debug

Describe pod:

```bash
kubectl describe pod <POD_NAME> -n coderaptor
```

View logs:

```bash
kubectl logs deploy/ai-service -n coderaptor
kubectl logs deploy/review-service -n coderaptor
kubectl logs deploy/auth-service -n coderaptor
kubectl logs deploy/execution-service -n coderaptor
kubectl logs deploy/frontend -n coderaptor
```

Check mounted Key Vault files:

```bash
kubectl exec deploy/ai-service -n coderaptor -- ls -l /mnt/secrets-store
```

Readiness checks:

```bash
kubectl port-forward svc/ai-service 8003:8003 -n coderaptor
curl http://localhost:8003/ready
```

## Important Notes

- Do not put real API keys in Kubernetes YAML.
- The app services read secrets from `/mnt/secrets-store`.
- PostgreSQL reads its password from `/mnt/secrets-store/POSTGRES_PASSWORD`.
- Auth and review services read `DATABASE_URL` from `/mnt/secrets-store/DATABASE_URL`.
- AI service reads Azure OpenAI settings from `/mnt/secrets-store`.
