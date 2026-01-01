resource "google_storage_bucket" "thoth_bucket" {
  name     = "thoth-storage-bucket"
  location = "US"

  force_destroy               = true
  public_access_prevention    = "enforced"
  uniform_bucket_level_access = true

  labels = {
    "project" : "thoth",
    "managed" : "terraform"
  }
}