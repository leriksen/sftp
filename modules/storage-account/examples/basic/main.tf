module "storage_account" {
  source = "../../"

  resource_group_name = var.resource_group_name
  sequence_no         = "01"
  location            = var.location

  tags = {
    environment = "dev"
  }
}
