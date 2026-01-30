# Infrastructure Documentation

This section covers the infrastructure-as-code setup for Thoth.

## Terraform Modules

The infrastructure is organized into three Terraform modules:

### Module Structure

```
terraform/
├── main.tf                 # Root module configuration
├── variables.tf            # Global variables
├── environments/
│   └── dev.tfvars          # Development environment
├── shared/                 # Shared resources module
├── mcp/                    # MCP Server module
└── ingestion/              # Ingestion Worker module
```

## Shared Module (`terraform/shared/`)

Provisions common infrastructure resources.

### Resources

| Resource | Type | Description |
|----------|------|-------------|
| `google_project_service` | API | Enables required GCP APIs |
| `google_service_account` | IAM | Service account for workloads |
| `google_storage_bucket` | Storage | Vector DB and file storage |
| `google_secret_manager_secret` | Secrets | GitLab and HuggingFace tokens |

### Outputs

| Output | Description |
|--------|-------------|
| `service_account_email` | Email of the created service account |
| `storage_bucket_name` | Name of the GCS bucket |
| `gitlab_token_secret_id` | Secret Manager ID for GitLab token |

## MCP Module (`terraform/mcp/`)

Provisions the MCP Server Cloud Run service.

### Resources

| Resource | Type | Description |
|----------|------|-------------|
| `google_cloud_run_v2_service` | Cloud Run | MCP server service |
| `google_cloud_run_service_iam_member` | IAM | Public access (if configured) |

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `mcp_cpu` | `2` | CPU allocation |
| `mcp_memory` | `2Gi` | Memory allocation |
| `mcp_min_instances` | `0` | Minimum instances |
| `mcp_max_instances` | `3` | Maximum instances |

## Ingestion Module (`terraform/ingestion/`)

Provisions the Ingestion Worker and Cloud Tasks queue.

### Resources

| Resource | Type | Description |
|----------|------|-------------|
| `google_cloud_run_v2_service` | Cloud Run | Ingestion worker service |
| `google_cloud_tasks_queue` | Tasks | Batch processing queue |

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ingestion_cpu` | `1` | CPU allocation |
| `ingestion_memory` | `2Gi` | Memory allocation |
| `cloud_tasks_max_concurrent` | `10` | Max concurrent task dispatches |
| `cloud_tasks_dispatch_rate` | `5` | Tasks per second |

## Terraform Cloud Setup

The project uses Terraform Cloud for state management and remote execution.

### Workspace Configuration

| Setting | Value |
|---------|-------|
| Organization | `TheWinterShadow` |
| Workspace | `thoth-mcp-gcp` |
| Execution Mode | Remote |

### Required Variables

Set these in Terraform Cloud workspace:

| Variable | Type | Description |
|----------|------|-------------|
| `GOOGLE_CREDENTIALS` | Environment (sensitive) | GCP service account JSON |
| `project_id` | Terraform | GCP project ID |
| `region` | Terraform | GCP region |

## Generating Terraform Documentation

Use `terraform-docs` to generate module documentation:

```bash
# Install terraform-docs
brew install terraform-docs

# Generate docs for all modules
terraform-docs markdown table terraform/shared > docs/source/infrastructure/shared.md
terraform-docs markdown table terraform/mcp > docs/source/infrastructure/mcp.md
terraform-docs markdown table terraform/ingestion > docs/source/infrastructure/ingestion.md
```

### terraform-docs Configuration

Add `.terraform-docs.yml` to each module:

```yaml
formatter: markdown table
output:
  file: README.md
  mode: inject

sort:
  enabled: true
  by: required

settings:
  indent: 2
  escape: true
  html: true
```
