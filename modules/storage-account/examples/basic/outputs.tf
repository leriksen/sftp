output "id" {
  value       = module.storage_account.id
  description = "Resource ID of the storage account."
}

output "umi_principal_id" {
  value       = module.storage_account.umi_principal_id
  description = "Principal ID of the user-assigned managed identity."
}
