output "storage_account_id" {
  value = module.storage_account.id
}

output "container_name" {
  value = azurerm_storage_container.sftp.name
}
