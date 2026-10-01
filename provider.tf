provider "azapi" {}

provider "azurerm" {
  resource_provider_registrations = "none"
  storage_use_azuread             = true
  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}
