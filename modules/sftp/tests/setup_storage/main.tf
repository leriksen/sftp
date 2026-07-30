module "storage_account" {
  source  = "app.terraform.io/leif-lab3/terraform-azurerm-storage-account/azurerm"
  version = "0.5.0"

  resource_group_name = var.resource_group_name
  location            = var.location
  sequence_no         = var.sequence_no
  sftp_enabled        = true
}

resource "azurerm_storage_container" "sftp" {
  name               = var.container_name
  storage_account_id = module.storage_account.id
}
