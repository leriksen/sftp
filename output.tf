# ---------------------------------------------------------------------------
# Keyed by storage account sequence_no ("01" = local users, "02" = Entra ID).
# tests/env-test.sh indexes "01", tests/entra/env-entra.sh indexes "02".
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

# ---------------------------------------------------------------------------
# Entra service principals backing account "02", keyed by
# entra_principals[].key. tests/entra/setup_creds.sh materialises the client
# IDs/secrets into dotfiles so the harness can `az login --service-principal`
# and mint an OpenSSH certificate per principal.
# ---------------------------------------------------------------------------

output "entra_sp_object_ids" {

  description = "Object ID of each created service principal (the role assignment principal_id), keyed by entra_principals[].key."

  value = { for k, sp in azuread_service_principal.this : k => sp.object_id }

}

output "entra_sp_client_ids" {

  description = "Application (client) ID of each created service principal, keyed by entra_principals[].key."

  value = { for k, a in azuread_application.this : k => a.client_id }

}

output "entra_sp_client_secrets" {

  description = "Client secret of each created service principal, keyed by entra_principals[].key."

  value     = { for k, p in azuread_application_password.this : k => p.value }
  sensitive = true
}
