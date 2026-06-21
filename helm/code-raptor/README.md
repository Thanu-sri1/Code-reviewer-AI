# Code Raptor Helm Chart

This chart deploys Code Raptor into two namespaces by default:

```text
codereviewer
codereviewer-secondary
```

Each service has a separate deployment template and service template under `templates/`.

## Render Locally

```bash
helm template code-raptor ./helm/code-raptor
```

## Install

```bash
helm install code-raptor ./helm/code-raptor
```

## Upgrade

```bash
helm upgrade code-raptor ./helm/code-raptor
```

Edit `values.yaml` to change namespaces, replica count, image registry, image tag, Key Vault settings, or ingress settings.
