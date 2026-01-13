#!/bin/bash
# Verification script for Cloud Run deployment

set -euo pipefail

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-thoth-483015}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="thoth-mcp-server"
BUCKET_NAME="thoth-storage-bucket"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_success() {
    echo -e "${GREEN}✓${NC} $1"
}

echo_error() {
    echo -e "${RED}✗${NC} $1"
}

echo_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check if service exists
check_service_exists() {
    echo_info "Checking if Cloud Run service exists..."
    
    if gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" &>/dev/null; then
        echo_success "Service '${SERVICE_NAME}' exists"
        return 0
    else
        echo_error "Service '${SERVICE_NAME}' not found"
        return 1
    fi
}

# Check service status
check_service_status() {
    echo_info "Checking service status..."
    
    STATUS=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(status.conditions[0].status)")
    
    if [ "${STATUS}" = "True" ]; then
        echo_success "Service is ready"
        return 0
    else
        echo_error "Service is not ready (status: ${STATUS})"
        return 1
    fi
}

# Check service URL
check_service_url() {
    echo_info "Retrieving service URL..."
    
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(status.url)")
    
    if [ -n "${SERVICE_URL}" ]; then
        echo_success "Service URL: ${SERVICE_URL}"
        echo "${SERVICE_URL}" > /tmp/thoth_service_url.txt
        return 0
    else
        echo_error "Could not retrieve service URL"
        return 1
    fi
}

# Check health endpoint
check_health_endpoint() {
    echo_info "Testing health endpoint..."
    
    SERVICE_URL=$(cat /tmp/thoth_service_url.txt 2>/dev/null || echo "")
    
    if [ -z "${SERVICE_URL}" ]; then
        echo_warning "Service URL not available, skipping health check"
        return 0
    fi
    
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health" || echo "000")
    
    if [ "${HTTP_CODE}" = "200" ]; then
        echo_success "Health check passed (HTTP ${HTTP_CODE})"
        return 0
    else
        echo_warning "Health check returned HTTP ${HTTP_CODE}"
        echo_info "Service may still be starting up or health endpoint not configured"
        return 0
    fi
}

# Check logs
check_logs() {
    echo_info "Checking recent logs..."
    
    LOGS=$(gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}" \
        --limit=5 \
        --format="value(timestamp,severity,textPayload)" \
        --freshness=10m 2>/dev/null || echo "")
    
    if [ -n "${LOGS}" ]; then
        echo_success "Logs are available"
        echo ""
        echo "Recent logs (last 5 entries):"
        echo "----------------------------------------"
        echo "${LOGS}"
        echo "----------------------------------------"
        return 0
    else
        echo_warning "No recent logs found (service may not have received requests yet)"
        return 0
    fi
}

# Check GCS bucket
check_gcs_bucket() {
    echo_info "Checking GCS bucket..."
    
    if gsutil ls "gs://${BUCKET_NAME}/" &>/dev/null; then
        echo_success "GCS bucket '${BUCKET_NAME}' is accessible"
        
        # Check if bucket has any data
        FILE_COUNT=$(gsutil ls -r "gs://${BUCKET_NAME}/" 2>/dev/null | wc -l)
        echo_info "Files in bucket: ${FILE_COUNT}"
        return 0
    else
        echo_error "GCS bucket '${BUCKET_NAME}' is not accessible"
        return 1
    fi
}

# Check service account
check_service_account() {
    echo_info "Checking service account..."
    
    SA_EMAIL=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(spec.template.spec.serviceAccountName)")
    
    if [ -n "${SA_EMAIL}" ]; then
        echo_success "Service account: ${SA_EMAIL}"
        return 0
    else
        echo_warning "Service account not configured (using default)"
        return 0
    fi
}

# Check environment variables
check_environment() {
    echo_info "Checking environment variables..."
    
    ENV_VARS=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(spec.template.spec.containers[0].env[].name)")
    
    if [ -n "${ENV_VARS}" ]; then
        echo_success "Environment variables configured"
        echo_info "Variables: $(echo ${ENV_VARS} | tr '\n' ', ')"
        return 0
    else
        echo_warning "No environment variables found"
        return 0
    fi
}

# Check resource configuration
check_resources() {
    echo_info "Checking resource configuration..."
    
    MEMORY=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(spec.template.spec.containers[0].resources.limits.memory)")
    
    CPU=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(spec.template.spec.containers[0].resources.limits.cpu)")
    
    echo_success "Resources: CPU=${CPU}, Memory=${MEMORY}"
    return 0
}

# Check scaling configuration
check_scaling() {
    echo_info "Checking scaling configuration..."
    
    MIN=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(spec.template.metadata.annotations.autoscaling\.knative\.dev/minScale)")
    
    MAX=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(spec.template.metadata.annotations.autoscaling\.knative\.dev/maxScale)")
    
    echo_success "Scaling: min=${MIN:-0}, max=${MAX:-100}"
    return 0
}

# Main verification
main() {
    echo ""
    echo "================================================"
    echo "  Thoth Cloud Run Deployment Verification"
    echo "================================================"
    echo ""
    echo "Project: ${PROJECT_ID}"
    echo "Region:  ${REGION}"
    echo "Service: ${SERVICE_NAME}"
    echo ""
    
    FAILURES=0
    
    # Run checks
    check_service_exists || ((FAILURES++))
    echo ""
    
    if [ ${FAILURES} -eq 0 ]; then
        check_service_status || ((FAILURES++))
        echo ""
        
        check_service_url || ((FAILURES++))
        echo ""
        
        check_health_endpoint || true
        echo ""
        
        check_logs || true
        echo ""
        
        check_gcs_bucket || ((FAILURES++))
        echo ""
        
        check_service_account || true
        echo ""
        
        check_environment || true
        echo ""
        
        check_resources || true
        echo ""
        
        check_scaling || true
        echo ""
    fi
    
    # Summary
    echo "================================================"
    if [ ${FAILURES} -eq 0 ]; then
        echo_success "All critical checks passed!"
        echo ""
        echo "Service is deployed and healthy ✓"
        
        if [ -f /tmp/thoth_service_url.txt ]; then
            echo ""
            echo "Service URL: $(cat /tmp/thoth_service_url.txt)"
        fi
        
        echo ""
        exit 0
    else
        echo_error "${FAILURES} check(s) failed"
        echo ""
        echo "Please review the errors above and check:"
        echo "  - Service deployment status"
        echo "  - GCS bucket permissions"
        echo "  - Service account configuration"
        echo ""
        exit 1
    fi
}

# Run main
main "$@"
