output "storage_account_id" {
  value = azurerm_storage_account.this.id
}

output "container_name" {
  value = azurerm_storage_container.sftp.name
}
