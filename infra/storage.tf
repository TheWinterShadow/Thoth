resource "google_storage_bucket" "thoth_bucket" {
  name     = var.bucket_name
  location = var.bucket_location

  force_destroy               = true
  public_access_prevention    = "enforced"
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    "project"    = "thoth"
    "managed-by" = "terraform"
  }
}

output "bucket_name" {
  description = "Name of the GCS bucket"
  value       = google_storage_bucket.thoth_bucket.name
}

output "bucket_url" {
  description = "URL of the GCS bucket"
  value       = google_storage_bucket.thoth_bucket.url
}
