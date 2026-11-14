terraform {
  backend "s3" {
    bucket       = "pierre-tf-state"
    key          = "powerlifting-app/ci-access.tfstate"
    region       = "ca-central-1"
    encrypt      = true
    use_lockfile = true
  }
}
