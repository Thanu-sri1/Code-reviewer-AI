# Code Raptor Helm Chart

The base values mirror the manifests in `k8s/` and deploy Code Raptor to:

```text
codereviewer
```

Use the environment-specific values files to deploy separately to
`dev-codereviewer` or `prod-codereviewer`.

Each service has a separate deployment template and service template under `templates/`.

## Render Locally

```bash
helm template code-raptor-dev ./helm/code-raptor -f ./helm/code-raptor/values-dev.yaml
helm template code-raptor-prod ./helm/code-raptor -f ./helm/code-raptor/values-prod.yaml
```

## Install

```bash
helm install code-raptor-dev ./helm/code-raptor -f ./helm/code-raptor/values-dev.yaml
helm install code-raptor-prod ./helm/code-raptor -f ./helm/code-raptor/values-prod.yaml
```

## Upgrade

```bash
helm upgrade code-raptor-dev ./helm/code-raptor -f ./helm/code-raptor/values-dev.yaml
helm upgrade code-raptor-prod ./helm/code-raptor -f ./helm/code-raptor/values-prod.yaml
```

Edit `values.yaml` to change namespaces, replica count, image registry, image tag, Key Vault settings, or ingress settings.
