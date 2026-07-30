output "storage_account_id" {

  value = one(values(module.storage_account)).id

}

#output "sftp_endpoint" {

# The published storage-account module has no name output, and no name
# override, so the account name is pulled back out of its resource ID
# ("…/storageAccounts/<name>") rather than threaded through as a variable.
#  value = "${regex("storageAccounts/([^/]+)$", one(values(module.storage_account)).id)}.blob.core.windows.net"

#}

output "local_user_ids" {

  description = "id assigned to each SFTP local user, keyed by sequence_number (0 = inbound, 1 = outbound)."

  value     = one(values(module.sftp_local_users)).local_user_ids
  sensitive = true
}

output "local_user_names" {

  description = "login name assigned to each SFTP local user (\"sftpuser<sequence_number>\"), keyed by sequence_number."

  value     = one(values(module.sftp_local_users)).local_user_names
  sensitive = true
}

output "filesystem_ids" {

  description = "Data Lake Gen2 filesystem (container) resource ID, keyed by container name."

  value = one(values(module.adls_filesystem)).filesystem_ids

}
