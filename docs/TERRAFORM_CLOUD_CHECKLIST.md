# Terraform Cloud Migration Checklist

Quick checklist to ensure your Terraform Cloud setup is complete.

## ✅ Completed

- [x] GCP Service Account created (`terraform-thoth@thoth-dev-485501.iam.gserviceaccount.com`)
- [x] Service Account key generated (`auth/terraform-key.json`)
- [x] Service Account key excluded from git (`.gitignore` updated)
- [x] GitHub Actions workflow updated to use Terraform Cloud
- [x] Documentation created

## 🔲 To Complete

### 1. Terraform Cloud Workspace Setup

- [ ] Create/verify Terraform Cloud organization: `TheWinterShadow`
- [ ] Create workspace: `thoth-mcp-gcp`
- [ ] Set Execution Mode to: **Remote**
- [ ] Set Terraform Version to: **1.5.7**
- [ ] Set Working Directory to: `terraform`

**URL**: https://app.terraform.io/app/TheWinterShadow/workspaces/thoth-mcp-gcp/settings/general

### 2. Configure Terraform Cloud Variables

Go to: https://app.terraform.io/app/TheWinterShadow/thoth-mcp-gcp/settings/variables

#### Environment Variables

- [ ] **GOOGLE_CREDENTIALS** (sensitive)
  - Type: Environment Variable
  - Value: Minified JSON (use: `cat auth/terraform-key.json | jq -c .`)
  - Mark as: Sensitive ✓

#### Terraform Variables (Optional - can use tfvars files instead)

- [ ] **project_id**: `thoth-dev-485501`
- [ ] **region**: `us-central1`
- [ ] **environment**: `dev`
- [ ] **container_image**: `gcr.io/thoth-dev-485501/thoth-mcp:latest`

### 3. GitHub Secrets Setup

Go to: https://github.com/TheWinterShadow/Thoth/settings/secrets/actions

- [ ] **TF_API_TOKEN**
  - Generate from: https://app.terraform.io/app/settings/tokens
  - Click: "Create an API token"
  - Copy token immediately
  - Add to GitHub Secrets

- [ ] **GOOGLE_APPLICATION_CREDENTIALS** (if not already set)
  - Same value as `GOOGLE_CREDENTIALS` above
  - Used for Cloud Run deployment steps

### 4. Test Local Terraform

```bash
# Authenticate with Terraform Cloud
terraform login

# Navigate to terraform directory
cd terraform

# Initialize (will connect to Terraform Cloud)
terraform init

# Run plan
terraform plan -var-file=environments/dev.tfvars

# If plan looks good, apply
terraform apply -var-file=environments/dev.tfvars
```

- [ ] `terraform login` successful
- [ ] `terraform init` connects to Terraform Cloud
- [ ] `terraform plan` runs without errors
- [ ] `terraform apply` completes successfully

### 5. Test GitHub Actions

```bash
# Make a small change and push
git add .
git commit -m "test: verify Terraform Cloud integration"
git push origin main
```

Then verify:

- [ ] GitHub Actions workflow triggers
- [ ] Build image job completes
- [ ] Terraform job completes
- [ ] Deploy Cloud Run job completes
- [ ] View run in Terraform Cloud: https://app.terraform.io/app/TheWinterShadow/thoth-mcp-gcp

### 6. Verify Deployment

- [ ] Cloud Run service is running: 
  ```bash
  gcloud run services describe thoth-mcp-server --region=us-central1
  ```

- [ ] Health check passes:
  ```bash
  curl $(gcloud run services describe thoth-mcp-server --region=us-central1 --format='value(status.url)')/health
  ```

- [ ] Check logs:
  ```bash
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=thoth-mcp-server" --limit=20
  ```

## 📚 Documentation

Reference these documents as needed:

- **[Terraform Cloud Setup](./TERRAFORM_CLOUD_SETUP.md)** - Complete setup guide
- **[GitHub Actions Terraform Cloud](./GITHUB_ACTIONS_TERRAFORM_CLOUD.md)** - GitHub Actions integration
- **[Terraform README](../terraform/README.md)** - Terraform directory documentation

## 🔒 Security Verification

- [ ] Service account key NOT committed to git
- [ ] `auth/` directory in `.gitignore`
- [ ] All secrets marked as sensitive in Terraform Cloud
- [ ] API tokens stored only in GitHub Secrets
- [ ] Service account has minimum required permissions

## 🎯 Success Criteria

You'll know everything is working when:

1. ✅ Local `terraform plan` runs successfully
2. ✅ Local `terraform apply` provisions infrastructure
3. ✅ GitHub Actions workflow completes without errors
4. ✅ Terraform Cloud shows successful runs
5. ✅ Cloud Run service is healthy and responding

## 🆘 Troubleshooting

If you encounter issues, check:

1. [Terraform Cloud Setup Guide](./TERRAFORM_CLOUD_SETUP.md#7-troubleshooting)
2. GitHub Actions logs: https://github.com/TheWinterShadow/Thoth/actions
3. Terraform Cloud runs: https://app.terraform.io/app/TheWinterShadow/thoth-mcp-gcp
4. GCP Console logs: https://console.cloud.google.com/logs

## Next Steps After Completion

- [ ] Set up production environment (`environments/prod.tfvars`)
- [ ] Configure separate Terraform Cloud workspace for production
- [ ] Set up monitoring and alerting
- [ ] Document runbooks for common operations
- [ ] Schedule regular secret rotation

---

**Last Updated**: January 25, 2026
