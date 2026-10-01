# ---------------------------------------------------------------------------
# Keyed by storage account sequence_no (only "01" now). Kept as maps rather
# than scalars so the outputs don't change shape if a second account returns;
# tests/env-test.sh indexes "01".
# ---------------------------------------------------------------------------

output "storage_account_ids" {

  description = "Storage account resource ID, keyed by sequence_no. The account name is the last path segment."

  value = { for k, m in module.storage_account : k => m.id }

}

output "local_user_ids" {

  description = "id assigned to each SFTP local user, keyed by sequence_no then sequence_number (0 = inbound, 1 = outbound)."

  value     = { for k, m in module.sftp_local_users : k => m.local_user_ids }
  sensitive = true
}

output "local_user_names" {

  description = "login name assigned to each SFTP local user (\"sftpuser<sequence_number>\"), keyed by sequence_no then sequence_number."

  value     = { for k, m in module.sftp_local_users : k => m.local_user_names }
  sensitive = true
}

output "filesystem_ids" {

  description = "Data Lake Gen2 filesystem (container) resource ID, keyed by sequence_no then container name."

  value = { for k, m in module.adls_filesystem : k => m.filesystem_ids }

}
