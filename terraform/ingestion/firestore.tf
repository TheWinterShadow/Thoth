# Firestore Configuration for Job Tracking
# Firestore is used by the ingestion worker to track job status and progress

# Enable Firestore API
resource "google_project_service" "firestore" {
  project            = var.project_id
  service            = "firestore.googleapis.com"
  disable_on_destroy = false
}

# Create Firestore database
# Note: Only one Firestore database can exist per project
# This creates a Firestore in Native mode (not Datastore mode)
resource "google_firestore_database" "thoth_jobs" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Prevent accidental deletion in production
  deletion_policy = "DELETE"

  depends_on = [google_project_service.firestore]
}

# Grant Firestore permissions to the service account
# The service account needs to create, read, update, and delete job documents
resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${var.service_account_email}"

  depends_on = [google_firestore_database.thoth_jobs]
}

# Optional: Create an index for efficient job queries
# Firestore automatically creates single-field indexes, but composite indexes
# need to be created explicitly if needed for complex queries
resource "google_firestore_index" "jobs_by_status_and_time" {
  project    = var.project_id
  database   = google_firestore_database.thoth_jobs.name
  collection = "thoth_jobs"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }

  depends_on = [google_firestore_database.thoth_jobs]
}

# Output Firestore database information
output "firestore_database_name" {
  description = "Name of the Firestore database"
  value       = google_firestore_database.thoth_jobs.name
}

output "firestore_location" {
  description = "Location of the Firestore database"
  value       = google_firestore_database.thoth_jobs.location_id
}
