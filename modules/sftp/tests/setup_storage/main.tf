resource "azurerm_storage_account" "this" {
  name                     = var.name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  is_hns_enabled           = true
  sftp_enabled             = true
}

resource "azurerm_storage_container" "sftp" {
  name               = var.container_name
  storage_account_id = azurerm_storage_account.this.id
}
