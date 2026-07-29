output "id" {
  value       = azurerm_storage_account.this.id
  description = "Resource ID of the storage account."
}

output "umi_id" {
  value       = azurerm_user_assigned_identity.this.id
  description = "Resource ID of the user-assigned managed identity."
}

output "umi_principal_id" {
  value       = azurerm_user_assigned_identity.this.principal_id
  description = "Principal ID of the user-assigned managed identity."
}
