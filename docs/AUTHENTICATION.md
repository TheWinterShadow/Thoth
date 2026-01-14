# Cloud Run IAM Authentication

The Thoth MCP Server uses **GCP Cloud Run's built-in IAM authentication** at the infrastructure level, similar to AWS API Gateway's authentication layer.

## How It Works

Authentication happens at the **Cloud Run ingress** before requests reach your container:

```
Internet Request → Cloud Run IAM Check → Your Container
                        ↓
                   403 if no valid
                   ID token provided
```

## Key Differences from Application-Level Auth

| Aspect | Application-Level | Infrastructure-Level (Current) |
|--------|-------------------|--------------------------------|
| Where auth happens | Inside your code | At Cloud Run ingress |
| What you manage | API keys, validation logic | IAM policies only |
| Auth token type | Custom (API keys, JWT) | Google Cloud ID tokens |
| Performance | Adds latency | No container overhead |
| Security | Depends on code quality | GCP-managed security |

## Granting Access

### To a User
```bash
gcloud run services add-iam-policy-binding thoth-mcp-server \
  --region=us-central1 \
  --member="user:email@example.com" \
  --role="roles/run.invoker"
```

### To a Service Account
```bash
gcloud run services add-iam-policy-binding thoth-mcp-server \
  --region=us-central1 \
  --member="serviceAccount:my-sa@project.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

### To a Google Group
```bash
gcloud run services add-iam-policy-binding thoth-mcp-server \
  --region=us-central1 \
  --member="group:team@example.com" \
  --role="roles/run.invoker"
```

## Making Authenticated Requests

### From gcloud CLI
```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://thoth-mcp-server-xxxxx.run.app/health
```

### From Application (with Service Account)
```python
import google.auth
import google.auth.transport.requests
import requests

# Get ID token for the service account
auth_req = google.auth.transport.requests.Request()
creds, project = google.auth.default()
creds.refresh(auth_req)
id_token = creds.id_token

# Make authenticated request
response = requests.get(
    "https://thoth-mcp-server-xxxxx.run.app/health",
    headers={"Authorization": f"Bearer {id_token}"}
)
```

### From Another Cloud Run Service
```python
import google.auth.transport.requests
import google.oauth2.id_token
import requests

# Get ID token for the target service
auth_req = google.auth.transport.requests.Request()
target_audience = "https://thoth-mcp-server-xxxxx.run.app"
id_token = google.oauth2.id_token.fetch_id_token(auth_req, target_audience)

# Make authenticated request
response = requests.get(
    f"{target_audience}/health",
    headers={"Authorization": f"Bearer {id_token}"}
)
```

## Revoking Access

```bash
gcloud run services remove-iam-policy-binding thoth-mcp-server \
  --region=us-central1 \
  --member="user:email@example.com" \
  --role="roles/run.invoker"
```

## Viewing Current Access

```bash
gcloud run services get-iam-policy thoth-mcp-server \
  --region=us-central1
```

## Security Benefits

1. **No secrets in code**: No API keys to manage, rotate, or accidentally commit
2. **Audit logging**: All access is logged in Cloud Audit Logs
3. **Fine-grained control**: Use Google Groups, service accounts, or individual users
4. **Automatic token refresh**: ID tokens are short-lived and managed by GCP
5. **Integration**: Works seamlessly with other GCP services

## Comparison to AWS API Gateway

| Feature | AWS API Gateway | GCP Cloud Run |
|---------|-----------------|---------------|
| Auth method | API Keys, Lambda Authorizers, Cognito | IAM, ID tokens |
| Token management | Manual API key rotation | Automatic (ID tokens) |
| Integration | AWS IAM | Google Cloud IAM |
| Audit logs | CloudTrail | Cloud Audit Logs |
| Cost | Per request | No additional cost |

## Troubleshooting

### Getting 403 Forbidden

1. Check you have the `run.invoker` role:
   ```bash
   gcloud run services get-iam-policy thoth-mcp-server --region=us-central1
   ```

2. Verify your ID token is valid:
   ```bash
   gcloud auth print-identity-token | jwt decode -
   ```

3. Check token expiration (ID tokens expire after 1 hour)

### For Programmatic Access

If calling from code, ensure your service account has:
- `roles/run.invoker` on the Cloud Run service
- Application Default Credentials configured

```bash
# Set application default credentials
gcloud auth application-default login
```

## Current Configuration

- **Service**: `thoth-mcp-server`
- **Region**: `us-central1`
- **URL**: Check `terraform output service_url`
- **Ingress**: ALL (publicly accessible URL, but IAM-protected)
- **Default Access**: Scheduler service account only
