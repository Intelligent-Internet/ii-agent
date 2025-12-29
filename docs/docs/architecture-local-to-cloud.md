# Architecture: Local to Cloud Deployment Path

This document outlines the architectural evolution of ii-agent from a local development setup to a production-ready cloud deployment, with emphasis on security considerations for sensitive/NDA-protected data.

## Overview

ii-agent supports multiple deployment models through a pluggable sandbox provider architecture:

| Stage | Sandbox Provider | Network Exposure | Data Location | Multi-tenant |
|-------|------------------|------------------|---------------|--------------|
| **Local Dev** | Docker | localhost only | Your machine | No |
| **Team/On-prem** | Docker + Auth | Internal network | Your infrastructure | Limited |
| **Cloud Production** | Kubernetes/gVisor | Internet-facing | Cloud VPC | Yes |

---

## Stage 1: Local Development (Current)

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Single Developer Machine                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Browser ──▶ Frontend (:1420)                                  │
│                   │                                              │
│                   ▼                                              │
│              Backend (:8000)                                     │
│                   │                                              │
│         ┌────────┴────────┐                                     │
│         ▼                 ▼                                      │
│   Sandbox-Server    Tool-Server                                 │
│      (:8100)          (:1236)                                   │
│         │                                                        │
│         │ Docker API                                            │
│         ▼                                                        │
│   ┌─────────────────────────────────────────┐                   │
│   │     Ephemeral Sandbox Containers        │                   │
│   │  ┌─────────┐ ┌─────────┐ ┌─────────┐   │                   │
│   │  │Sandbox 1│ │Sandbox 2│ │   ...   │   │                   │
│   │  └─────────┘ └─────────┘ └─────────┘   │                   │
│   └─────────────────────────────────────────┘                   │
│                                                                  │
│   ┌──────────┐  ┌───────┐  ┌────────────────┐                  │
│   │ Postgres │  │ Redis │  │ Your MCP Server│                  │
│   │  (:5433) │  │(:6379)│  │    (:6060)     │                  │
│   └──────────┘  └───────┘  └────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Security Model

| Aspect | Implementation | Risk Level |
|--------|----------------|------------|
| Network exposure | localhost only | ✅ Low |
| Authentication | JWT (optional demo mode) | ⚠️ Acceptable for dev |
| Sandbox isolation | Docker containers | ⚠️ Process-level |
| Data at rest | Local filesystem | ✅ Your control |
| Secrets | Environment variables | ⚠️ Acceptable for dev |

### What Works Now

- ✅ Full agent functionality without E2B/ngrok
- ✅ Local MCP server connectivity
- ✅ File operations with path traversal protection
- ✅ Command execution in isolated containers
- ✅ Resource limits (memory, CPU, PIDs)
- ✅ Basic capability dropping
- ✅ **Orphan cleanup** - Automatic removal of sandboxes when sessions are deleted
- ✅ **Local storage** - Files stored locally instead of cloud storage (GCS)
- ✅ **Port pool management** - Dynamic port allocation (30000-30999) for sandbox services

### Known Limitations

- Docker socket mount gives sandbox-server root-equivalent host access
- No network policy between sandbox containers
- No audit logging
- Single-user only

### Quick Start

```bash
# Build sandbox image
docker build -t ii-agent-sandbox:latest -f e2b.Dockerfile .

# Configure
cp docker/.stack.env.local.example docker/.stack.env.local
# Edit: add JWT_SECRET_KEY and LLM API key

# Run
docker compose -f docker/docker-compose.local-only.yaml \
  --env-file docker/.stack.env.local up -d
```

---

## Stage 2: Team/On-Premises Deployment

### Architecture Changes

```
┌─────────────────────────────────────────────────────────────────┐
│                    Internal Network / VPN                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────────────────────────────┐                      │
│   │          Reverse Proxy (nginx)       │                      │
│   │   - TLS termination                  │                      │
│   │   - Rate limiting                    │                      │
│   │   - IP allowlisting                  │                      │
│   └─────────────────┬────────────────────┘                      │
│                     │                                            │
│         ┌───────────┴───────────┐                               │
│         ▼                       ▼                                │
│   ┌──────────┐           ┌──────────┐                           │
│   │ Frontend │           │ Backend  │                           │
│   └──────────┘           └────┬─────┘                           │
│                               │                                  │
│                    ┌──────────┴──────────┐                      │
│                    ▼                     ▼                       │
│             Sandbox-Server         Tool-Server                   │
│             (+ mTLS auth)          (+ mTLS auth)                │
│                    │                                             │
│                    ▼                                             │
│   ┌─────────────────────────────────────────┐                   │
│   │  Sandboxes (isolated Docker network)    │                   │
│   │  - No inter-container communication     │                   │
│   │  - Egress restricted to MCP only        │                   │
│   └─────────────────────────────────────────┘                   │
│                                                                  │
│   ┌──────────┐  ┌───────┐  ┌────────────────┐                  │
│   │ Postgres │  │ Redis │  │   MCP Server   │                  │
│   │ (TLS)    │  │ (TLS) │  │ (internal only)│                  │
│   └──────────┘  └───────┘  └────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Required Changes

#### 1. Add Service-to-Service Authentication

```yaml
# docker-compose.team.yaml additions
services:
  sandbox-server:
    environment:
      # Require mTLS or JWT for API calls
      REQUIRE_AUTH: "true"
      AUTH_JWT_SECRET: ${SANDBOX_AUTH_SECRET}
```

#### 2. Create Isolated Docker Network

```yaml
networks:
  sandbox-net:
    driver: bridge
    internal: true  # No external access
    driver_opts:
      com.docker.network.bridge.enable_icc: "false"  # No inter-container
```

#### 3. Add Reverse Proxy with TLS

```nginx
# nginx.conf
upstream backend {
    server backend:8000;
}

server {
    listen 443 ssl;
    ssl_certificate /etc/ssl/certs/ii-agent.crt;
    ssl_certificate_key /etc/ssl/private/ii-agent.key;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    
    location /api/ {
        limit_req zone=api burst=20;
        proxy_pass http://backend;
    }
}
```

#### 4. Implement Audit Logging

```python
# Add to sandbox-server
import structlog

logger = structlog.get_logger()

async def create_sandbox(..., user_id: str):
    logger.info(
        "sandbox_created",
        user_id=user_id,
        sandbox_id=sandbox_id,
        action="create"
    )
```

### Security Improvements

| Aspect | Change | Risk Reduction |
|--------|--------|----------------|
| Network | TLS everywhere, mTLS for services | High |
| Authentication | OIDC/SAML integration | High |
| Network isolation | Isolated Docker network | Medium |
| Audit | Structured logging to SIEM | Medium |
| Rate limiting | Nginx/HAProxy rate limits | Medium |

---

## Stage 3: Cloud Production (AWS/GCP/Azure)

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              AWS VPC                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    Public Subnet                                 │   │
│   │   ┌─────────────┐                                               │   │
│   │   │     ALB     │◀── WAF + Shield                               │   │
│   │   │  (HTTPS)    │                                               │   │
│   │   └──────┬──────┘                                               │   │
│   └──────────┼──────────────────────────────────────────────────────┘   │
│              │                                                           │
│   ┌──────────┼──────────────────────────────────────────────────────┐   │
│   │          │           Private Subnet (EKS)                        │   │
│   │          ▼                                                       │   │
│   │   ┌─────────────────────────────────────────────────────────┐   │   │
│   │   │                    EKS Cluster                           │   │   │
│   │   │                                                          │   │   │
│   │   │   ┌──────────┐  ┌──────────────┐  ┌──────────────┐     │   │   │
│   │   │   │ Frontend │  │   Backend    │  │ Tool-Server  │     │   │   │
│   │   │   │  (Pod)   │  │    (Pod)     │  │    (Pod)     │     │   │   │
│   │   │   └──────────┘  └──────┬───────┘  └──────────────┘     │   │   │
│   │   │                        │                                 │   │   │
│   │   │                        ▼                                 │   │   │
│   │   │              ┌─────────────────┐                        │   │   │
│   │   │              │ Sandbox-Server  │                        │   │   │
│   │   │              │ (Pod + IAM Role)│                        │   │   │
│   │   │              └────────┬────────┘                        │   │   │
│   │   │                       │                                  │   │   │
│   │   │   ┌───────────────────┴───────────────────┐             │   │   │
│   │   │   │        Sandbox Namespace               │             │   │   │
│   │   │   │   ┌─────────┐  ┌─────────┐            │             │   │   │
│   │   │   │   │Sandbox 1│  │Sandbox 2│  ...       │◀─┐         │   │   │
│   │   │   │   │ (gVisor)│  │ (gVisor)│            │  │         │   │   │
│   │   │   │   └─────────┘  └─────────┘            │  │         │   │   │
│   │   │   │                                        │  │         │   │   │
│   │   │   │   NetworkPolicy: deny-all + allow-mcp │  │         │   │   │
│   │   │   └────────────────────────────────────────┘  │         │   │   │
│   │   │                                               │         │   │   │
│   │   └───────────────────────────────────────────────┼─────────┘   │   │
│   │                                                   │             │   │
│   │   ┌────────────────┐  ┌────────────────┐         │             │   │
│   │   │   RDS Postgres │  │  ElastiCache   │         │             │   │
│   │   │  (encrypted)   │  │    (Redis)     │         │             │   │
│   │   └────────────────┘  └────────────────┘         │             │   │
│   │                                                   │             │   │
│   └───────────────────────────────────────────────────┼─────────────┘   │
│                                                       │                  │
│   ┌───────────────────────────────────────────────────┼─────────────┐   │
│   │                    Private Subnet (Data)          │             │   │
│   │                                                   ▼             │   │
│   │   ┌────────────────────────────────────────────────────────┐   │   │
│   │   │              Your MCP Server (Fargate)                  │   │   │
│   │   │   - IAM Role for data access                           │   │   │
│   │   │   - VPC endpoint for S3/Secrets Manager                │   │   │
│   │   │   - No internet access                                 │   │   │
│   │   └────────────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

External Services (via VPC Endpoints):
├── AWS Secrets Manager (API keys)
├── CloudWatch (logs, metrics)
├── S3 (artifacts, optional)
└── ECR (container images)
```

### Implementation Requirements

#### 1. Kubernetes Sandbox Provider

Replace Docker provider with Kubernetes-native sandbox management:

```python
# src/ii_sandbox_server/sandboxes/kubernetes.py (new file)
class KubernetesSandbox(BaseSandbox):
    """
    Kubernetes-native sandbox provider.
    
    Creates pods with gVisor runtime for VM-level isolation
    without the overhead of actual VMs.
    """
    
    async def create(self, ...):
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": f"sandbox-{sandbox_id}",
                "namespace": "ii-agent-sandboxes",
                "labels": {"ii-agent.sandbox": "true"}
            },
            "spec": {
                "runtimeClassName": "gvisor",  # VM-level isolation
                "securityContext": {
                    "runAsNonRoot": True,
                    "seccompProfile": {"type": "RuntimeDefault"}
                },
                "containers": [{
                    "name": "sandbox",
                    "image": self.config.sandbox_image,
                    "resources": {
                        "limits": {"memory": "2Gi", "cpu": "2"},
                        "requests": {"memory": "512Mi", "cpu": "0.5"}
                    },
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "capabilities": {"drop": ["ALL"]}
                    }
                }]
            }
        }
```

#### 2. Network Policies

```yaml
# k8s/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sandbox-isolation
  namespace: ii-agent-sandboxes
spec:
  podSelector:
    matchLabels:
      ii-agent.sandbox: "true"
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ii-agent-system
          podSelector:
            matchLabels:
              app: sandbox-server
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
    # Allow MCP server only
    - to:
        - namespaceSelector:
            matchLabels:
              name: ii-agent-data
          podSelector:
            matchLabels:
              app: mcp-server
      ports:
        - protocol: TCP
          port: 6060
```

#### 3. Pod Security Standards

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ii-agent-sandboxes
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: latest
```

#### 4. IAM Roles for Service Accounts (IRSA)

```yaml
# k8s/service-account.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: sandbox-server
  namespace: ii-agent-system
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/ii-agent-sandbox-server
---
# IAM Policy (Terraform)
resource "aws_iam_role_policy" "sandbox_server" {
  role = aws_iam_role.sandbox_server.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "arn:aws:secretsmanager:*:*:secret:ii-agent/*"
        ]
      }
    ]
  })
}
```

#### 5. Secrets Management

```python
# src/ii_sandbox_server/config.py additions
import boto3

def get_secret(secret_name: str) -> str:
    """Retrieve secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']

# Usage
config = SandboxConfig(
    jwt_secret=get_secret("ii-agent/jwt-secret"),
    # Never in environment variables
)
```

### Security Comparison

| Aspect | Local Docker | Cloud K8s |
|--------|--------------|-----------|
| Container isolation | Process namespace | gVisor (VM-level) |
| Network isolation | Bridge network | NetworkPolicy (deny-all) |
| Host access | Docker socket (root) | No host access |
| Secrets | Env vars | Secrets Manager + IRSA |
| Multi-tenant | ❌ No | ✅ Yes (namespace isolation) |
| Audit logging | Optional | CloudWatch + CloudTrail |
| Compliance | Manual | SOC2/HIPAA capable |

---

## Migration Checklist

### Local → Team

- [ ] Generate TLS certificates (or use Let's Encrypt)
- [ ] Configure reverse proxy with rate limiting
- [ ] Set up OIDC/SAML authentication
- [ ] Create isolated Docker network for sandboxes
- [ ] Implement audit logging
- [ ] Document incident response procedures

### Team → Cloud

- [ ] Provision EKS cluster with gVisor runtime
- [ ] Implement KubernetesSandbox provider
- [ ] Configure NetworkPolicies
- [ ] Set up IRSA for service accounts
- [ ] Migrate secrets to Secrets Manager
- [ ] Configure CloudWatch logging
- [ ] Set up ALB with WAF
- [ ] Implement horizontal pod autoscaling
- [ ] Configure pod disruption budgets
- [ ] Set up monitoring (Prometheus/Grafana or CloudWatch)
- [ ] Penetration testing
- [ ] Compliance review (if required)

---

## Cost Considerations

| Component | Local | Team (On-prem) | Cloud (AWS) |
|-----------|-------|----------------|-------------|
| Compute | Your hardware | Your servers | ~$200-500/mo (EKS + nodes) |
| Database | Docker | Your DB | ~$50-200/mo (RDS) |
| Networking | Free | Your network | ~$20-50/mo (NAT, ALB) |
| Secrets | N/A | HashiCorp Vault | ~$5/mo (Secrets Manager) |
| Monitoring | Local | Prometheus | ~$50-100/mo (CloudWatch) |
| **Total** | **$0** | **Your infra** | **~$325-850/mo** |

---

## Timeline Estimate

| Phase | Effort | Prerequisites |
|-------|--------|---------------|
| Local (done) | 0 | Docker installed |
| Team deployment | 1-2 weeks | TLS certs, auth provider |
| Cloud MVP | 2-4 weeks | AWS account, K8s experience |
| Production hardening | 2-4 weeks | Security review, compliance |

---

## References

- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [gVisor Container Sandbox](https://gvisor.dev/)
- [AWS EKS Best Practices](https://aws.github.io/aws-eks-best-practices/)
- [OWASP Container Security](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
