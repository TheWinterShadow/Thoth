terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }
}

provider "google" {
  project = "thoth-483015"
  region  = "us-central1"
  zone    = "us-central1-c"
}
