#!/bin/bash
# Setup script for Secrets Manager and Cloud Scheduler

set -euo pipefail

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-thoth-483015}"
REGION="${GCP_REGION:-us-central1}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    echo_step "Checking prerequisites..."
    
    if ! command -v gcloud &> /dev/null; then
        echo_error "gcloud CLI not found. Please install Google Cloud SDK."
        exit 1
    fi
    
    echo_info "Prerequisites check passed."
}

# Configure gcloud
configure_gcloud() {
    echo_step "Configuring gcloud..."
    
    gcloud config set project "${PROJECT_ID}"
    
    echo_info "gcloud configured for project: ${PROJECT_ID}"
}

# Enable required APIs
enable_apis() {
    echo_step "Enabling required APIs..."
    
    echo_info "Enabling Secret Manager API..."
    gcloud services enable secretmanager.googleapis.com --project="${PROJECT_ID}"
    
    echo_info "Enabling Cloud Scheduler API..."
    gcloud services enable cloudscheduler.googleapis.com --project="${PROJECT_ID}"
    
    echo_info "Enabling Cloud Run API..."
    gcloud services enable run.googleapis.com --project="${PROJECT_ID}"
    
    echo_info "All required APIs enabled."
}

# Setup Secret Manager
setup_secret_manager() {
    echo_step "Setting up Secret Manager..."
    
    # GitLab Token
    echo_info "Creating GitLab token secret..."
    if gcloud secrets describe gitlab-token --project="${PROJECT_ID}" &>/dev/null; then
        echo_warn "Secret 'gitlab-token' already exists."
    else
        gcloud secrets create gitlab-token \
            --replication-policy="automatic" \
            --project="${PROJECT_ID}"
        echo_info "Secret 'gitlab-token' created."
    fi
    
    # Prompt for GitLab token
    echo_warn "Please enter your GitLab personal access token (or press Enter to skip):"
    read -s GITLAB_TOKEN
    if [ -n "${GITLAB_TOKEN}" ]; then
        echo -n "${GITLAB_TOKEN}" | gcloud secrets versions add gitlab-token \
            --data-file=- \
            --project="${PROJECT_ID}"
        echo_info "GitLab token stored in Secret Manager."
    else
        echo_warn "Skipped GitLab token setup. You can add it later with:"
        echo "  echo -n 'YOUR_TOKEN' | gcloud secrets versions add gitlab-token --data-file=- --project=${PROJECT_ID}"
    fi
    
    # GitLab URL
    echo_info "Creating GitLab URL secret..."
    if gcloud secrets describe gitlab-url --project="${PROJECT_ID}" &>/dev/null; then
        echo_warn "Secret 'gitlab-url' already exists."
    else
        gcloud secrets create gitlab-url \
            --replication-policy="automatic" \
            --project="${PROJECT_ID}"
        echo_info "Secret 'gitlab-url' created."
        
        # Set default value
        echo -n "https://gitlab.com" | gcloud secrets versions add gitlab-url \
            --data-file=- \
            --project="${PROJECT_ID}"
        echo_info "GitLab URL set to default (https://gitlab.com)."
    fi
    
    # Google Credentials (optional)
    echo_info "Creating Google credentials secret..."
    if gcloud secrets describe google-application-credentials --project="${PROJECT_ID}" &>/dev/null; then
        echo_warn "Secret 'google-application-credentials' already exists."
    else
        gcloud secrets create google-application-credentials \
            --replication-policy="automatic" \
            --project="${PROJECT_ID}"
        echo_info "Secret 'google-application-credentials' created."
        
        # Set placeholder
        echo -n "{}" | gcloud secrets versions add google-application-credentials \
            --data-file=- \
            --project="${PROJECT_ID}"
        echo_info "Google credentials secret created with placeholder."
    fi
}

# Grant service account access to secrets
grant_secret_access() {
    echo_step "Granting service account access to secrets..."
    
    SERVICE_ACCOUNT="thoth-mcp-sa@${PROJECT_ID}.iam.gserviceaccount.com"
    
    echo_info "Granting access to gitlab-token..."
    gcloud secrets add-iam-policy-binding gitlab-token \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="${PROJECT_ID}"
    
    echo_info "Granting access to gitlab-url..."
    gcloud secrets add-iam-policy-binding gitlab-url \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="${PROJECT_ID}"
    
    echo_info "Granting access to google-application-credentials..."
    gcloud secrets add-iam-policy-binding google-application-credentials \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="${PROJECT_ID}"
    
    echo_info "Service account access granted."
}

# Setup Cloud Scheduler
setup_scheduler() {
    echo_step "Setting up Cloud Scheduler..."
    
    # Get Cloud Run service URL
    SERVICE_NAME="thoth-mcp-server"
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(status.url)" \
        --project="${PROJECT_ID}" 2>/dev/null || echo "")
    
    if [ -z "${SERVICE_URL}" ]; then
        echo_warn "Cloud Run service '${SERVICE_NAME}' not found. Please deploy the service first."
        echo_warn "Skipping scheduler setup."
        return
    fi
    
    echo_info "Cloud Run service URL: ${SERVICE_URL}"
    
    # Create scheduler service account if it doesn't exist
    SCHEDULER_SA="thoth-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
    if gcloud iam service-accounts describe "${SCHEDULER_SA}" --project="${PROJECT_ID}" &>/dev/null; then
        echo_info "Scheduler service account already exists."
    else
        echo_info "Creating scheduler service account..."
        gcloud iam service-accounts create thoth-scheduler \
            --display-name="Thoth Cloud Scheduler Service Account" \
            --project="${PROJECT_ID}"
    fi
    
    # Grant invoker role to scheduler service account
    echo_info "Granting Cloud Run invoker role to scheduler service account..."
    gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
        --member="serviceAccount:${SCHEDULER_SA}" \
        --role="roles/run.invoker" \
        --region="${REGION}" \
        --project="${PROJECT_ID}"
    
    # Create daily sync job
    echo_info "Creating daily sync scheduler job..."
    if gcloud scheduler jobs describe thoth-daily-sync --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
        echo_warn "Daily sync job already exists. Updating..."
        gcloud scheduler jobs update http thoth-daily-sync \
            --location="${REGION}" \
            --schedule="0 2 * * *" \
            --time-zone="UTC" \
            --uri="${SERVICE_URL}/sync" \
            --http-method=POST \
            --message-body='{"scheduled":true,"sync_type":"daily"}' \
            --oidc-service-account-email="${SCHEDULER_SA}" \
            --oidc-token-audience="${SERVICE_URL}" \
            --project="${PROJECT_ID}"
    else
        gcloud scheduler jobs create http thoth-daily-sync \
            --location="${REGION}" \
            --schedule="0 2 * * *" \
            --time-zone="UTC" \
            --uri="${SERVICE_URL}/sync" \
            --http-method=POST \
            --message-body='{"scheduled":true,"sync_type":"daily"}' \
            --oidc-service-account-email="${SCHEDULER_SA}" \
            --oidc-token-audience="${SERVICE_URL}" \
            --project="${PROJECT_ID}"
    fi
    echo_info "Daily sync job configured (runs at 2 AM UTC daily)."
    
    # Create hourly incremental sync job
    echo_info "Creating hourly incremental sync scheduler job..."
    if gcloud scheduler jobs describe thoth-hourly-incremental-sync --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
        echo_warn "Hourly sync job already exists. Updating..."
        gcloud scheduler jobs update http thoth-hourly-incremental-sync \
            --location="${REGION}" \
            --schedule="0 * * * *" \
            --time-zone="UTC" \
            --uri="${SERVICE_URL}/sync" \
            --http-method=POST \
            --message-body='{"scheduled":true,"sync_type":"incremental","incremental":true}' \
            --oidc-service-account-email="${SCHEDULER_SA}" \
            --oidc-token-audience="${SERVICE_URL}" \
            --project="${PROJECT_ID}"
    else
        gcloud scheduler jobs create http thoth-hourly-incremental-sync \
            --location="${REGION}" \
            --schedule="0 * * * *" \
            --time-zone="UTC" \
            --uri="${SERVICE_URL}/sync" \
            --http-method=POST \
            --message-body='{"scheduled":true,"sync_type":"incremental","incremental":true}' \
            --oidc-service-account-email="${SCHEDULER_SA}" \
            --oidc-token-audience="${SERVICE_URL}" \
            --project="${PROJECT_ID}"
    fi
    echo_info "Hourly incremental sync job configured (runs every hour)."
}

# Display summary
display_summary() {
    echo ""
    echo_step "Setup Summary"
    echo ""
    echo_info "✓ Secret Manager configured with secrets:"
    echo "  - gitlab-token"
    echo "  - gitlab-url"
    echo "  - google-application-credentials"
    echo ""
    echo_info "✓ Cloud Scheduler jobs created:"
    echo "  - thoth-daily-sync (2 AM UTC daily)"
    echo "  - thoth-hourly-incremental-sync (every hour)"
    echo ""
    echo_info "Next steps:"
    echo "  1. Update GitLab token if you skipped it:"
    echo "     echo -n 'YOUR_TOKEN' | gcloud secrets versions add gitlab-token --data-file=- --project=${PROJECT_ID}"
    echo ""
    echo "  2. Test scheduler jobs:"
    echo "     gcloud scheduler jobs run thoth-daily-sync --location=${REGION} --project=${PROJECT_ID}"
    echo ""
    echo "  3. View scheduler job logs:"
    echo "     gcloud logging read 'resource.type=cloud_scheduler_job' --limit=10 --project=${PROJECT_ID}"
    echo ""
    echo "  4. Manage secrets:"
    echo "     gcloud secrets list --project=${PROJECT_ID}"
    echo "     gcloud secrets versions access latest --secret=gitlab-token --project=${PROJECT_ID}"
    echo ""
}

# Main setup flow
main() {
    echo_info "Starting Secrets Manager and Cloud Scheduler setup..."
    echo_info "Project: ${PROJECT_ID}"
    echo_info "Region: ${REGION}"
    echo ""
    
    check_prerequisites
    configure_gcloud
    enable_apis
    setup_secret_manager
    grant_secret_access
    setup_scheduler
    display_summary
    
    echo ""
    echo_info "Setup complete! ✓"
}

# Run main function
main "$@"
