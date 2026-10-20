provider "azapi" {}

# Picks up the same ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID as
# azurerm. The Terraform SP needs Microsoft Graph Application.ReadWrite.OwnedBy
# (or broader), admin-consented, for the applications/service principals in
# entra.tf.
provider "azuread" {}

provider "azurerm" {
  resource_provider_registrations = "none"
  storage_use_azuread             = true
  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}
