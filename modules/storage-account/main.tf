resource "azurerm_user_assigned_identity" "this" {
  name                = "tftest-umi-${var.sequence_no}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  # Destroy order: azurerm_storage_account.this references this identity via
  # identity_ids, creating an implicit Terraform dependency that guarantees the
  # storage account is destroyed BEFORE this identity. This is intentional — if
  # CMK encryption is enabled, the identity must remain valid until the storage
  # account (and its Key Vault access) is fully removed. Do not remove the
  # identity_ids reference from the storage account without preserving an
  # explicit depends_on, or this ordering guarantee is lost.
}

resource "azurerm_storage_account" "this" {
  # Local fork of the published module: `name` defaults to the upstream
  # "<resource_group_name>dl<sequence_no>" pattern, but can be overridden to
  # adopt an already-existing storage account without forcing a
  # destroy/recreate (name is ForceNew).
  name                            = coalesce(var.name, "${var.resource_group_name}dl${var.sequence_no}")
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  is_hns_enabled                  = true
  sftp_enabled                    = var.sftp_enabled
  local_user_enabled              = var.sftp_enabled
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  blob_properties {
    change_feed_enabled = false
    # change_feed_retention_in_days = 7
    delete_retention_policy {
      days = 7
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this.id]
  }

  tags = var.tags
}
