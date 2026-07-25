output "storage_account_id" {

  value = azurerm_storage_account.this.id

}

output "sftp_endpoint" {

  value = "${var.storage_account_name}.blob.core.windows.net"

}

output "local_user_sids" {

  description = "SID assigned to each SFTP local user (used in POSIX ACLs)."

  value       = { for k, v in azurerm_storage_account_local_user.this : k => v.sid }
  sensitive   = true
}

output "local_user_ids" {

  description = "id assigned to each SFTP local user (used in POSIX ACLs)."

  value       = { for k, v in azurerm_storage_account_local_user.this : k => v.id }
  sensitive   = true
}

output "local_user_names" {

  description = "name assigned to each SFTP local user (used in POSIX ACLs)."

  value       = { for k, v in azurerm_storage_account_local_user.this : k => v.name }
  sensitive   = true
}
