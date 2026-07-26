module "adls_filesystem" {
  source = "../../"

  storage_account_id = var.storage_account_id

  containers = [
    { container_name = "silver" },
    { container_name = "gold" },
  ]

  paths = [
    { container_name = "silver", path_name = "landing" },
  ]
}
