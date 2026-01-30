# GCP Configuration (REQUIRED)
project_id = "thoth-dev-485501"
region     = "us-central1"
environment = "dev"

# Container Images (REQUIRED)
mcp_container_image        = "gcr.io/thoth-dev-485501/thoth-mcp:latest"
ingestion_container_image  = "gcr.io/thoth-dev-485501/thoth-ingestion:latest"

# GitLab Configuration (OPTIONAL - can also be set via Secret Manager UI)
# gitlab_token = "your-gitlab-personal-access-token"
# gitlab_url   = "https://gitlab.com"

# Application Configuration
log_level = "INFO"

# MCP Server Configuration
mcp_cpu          = "0.25"
mcp_memory       = "256Mi"
mcp_min_instances = 0
mcp_max_instances = 2

# Ingestion Worker Configuration
ingestion_cpu          = "1"
ingestion_memory       = "2Gi"
ingestion_min_instances = 0
ingestion_max_instances = 10

# Cloud Tasks Configuration
cloud_tasks_max_concurrent = 10
cloud_tasks_dispatch_rate  = 5
