provider "kubernetes" {}

provider "kubectl" {}

provider "helm" {
  kubernetes {}
}
