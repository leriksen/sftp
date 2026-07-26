output "local_user_ids" {
  value       = { for k, v in azurerm_storage_account_local_user.this : k => v.id }
  description = "Map of sequence_number to resource ID for each created local user."
}

output "local_user_names" {
  value       = { for k, v in azurerm_storage_account_local_user.this : k => v.name }
  description = "Map of sequence_number to name for each created local user."
}
