# Kubernetes Deployment — Customer Success Digital FTE

## Prerequisites

- Kubernetes cluster (1.27+)
- `kubectl` configured with cluster access
- Container image pushed to your registry
- nginx ingress controller installed
- cert-manager installed (for TLS)

## Deploy Step by Step

```bash
# 1. Create the namespace
kubectl apply -f namespace.yaml

# 2. Create secrets (edit values first!)
# IMPORTANT: Replace all placeholder values in secrets.yaml before applying
kubectl apply -f secrets.yaml

# 3. Create config map
kubectl apply -f configmap.yaml

# 4. Deploy PostgreSQL (wait for it to be ready)
kubectl apply -f postgres.yaml
kubectl wait --for=condition=ready pod -l component=postgres -n customer-success-fte --timeout=120s

# 5. Deploy API servers
kubectl apply -f deployment-api.yaml

# 6. Deploy message processor workers
kubectl apply -f deployment-worker.yaml

# 7. Deploy metrics collector
kubectl apply -f deployment-metrics.yaml

# 8. Create the service
kubectl apply -f service.yaml

# 9. Create the ingress (update domain in ingress.yaml first)
kubectl apply -f ingress.yaml

# 10. Enable autoscaling
kubectl apply -f hpa.yaml
```

## Or apply everything at once

```bash
kubectl apply -f namespace.yaml
# Edit secrets.yaml with real values first!
kubectl apply -f .
```

## Check Status

```bash
# View all pods
kubectl get pods -n customer-success-fte

# View deployments
kubectl get deployments -n customer-success-fte

# View services
kubectl get svc -n customer-success-fte

# View HPA status
kubectl get hpa -n customer-success-fte
```

## View Logs

```bash
# API server logs
kubectl logs -f deployment/fte-api -n customer-success-fte

# Message processor logs
kubectl logs -f deployment/fte-message-processor -n customer-success-fte

# Metrics collector logs
kubectl logs -f deployment/fte-metrics-collector -n customer-success-fte

# PostgreSQL logs
kubectl logs -f statefulset/postgres -n customer-success-fte
```

## Scale Manually

```bash
# Scale message processors (e.g., during high traffic)
kubectl scale deployment/fte-message-processor --replicas=5 -n customer-success-fte

# Scale API servers
kubectl scale deployment/fte-api --replicas=5 -n customer-success-fte
```

## Run Database Migration

```bash
# Port-forward to PostgreSQL
kubectl port-forward svc/postgres 5432:5432 -n customer-success-fte

# Then run the migration locally
psql -h localhost -U fte -d fte_db -f database/migrations/001_initial_schema.sql
```

## Architecture

```
                 ┌─────────────┐
  Internet ──────│   Ingress   │
                 └──────┬──────┘
                        │
                 ┌──────▼──────┐
                 │  Service    │
                 │  (ClusterIP)│
                 └──────┬──────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
     ┌────▼───┐   ┌────▼───┐   ┌────▼───┐
     │ API #1 │   │ API #2 │   │ API #3 │   ← HPA: 3-20 pods
     └────┬───┘   └────┬───┘   └────┬───┘
          │             │             │
          └─────────────┼─────────────┘
                        │
                 ┌──────▼──────┐
                 │    Kafka    │
                 └──────┬──────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
     ┌────▼───┐   ┌────▼───┐   ┌────▼───┐
     │Worker 1│   │Worker 2│   │Worker 3│   ← HPA: 3-30 pods
     └────────┘   └────────┘   └────────┘
                        │
                 ┌──────▼──────┐
                 │  PostgreSQL │
                 │  (pgvector) │
                 └─────────────┘
```
