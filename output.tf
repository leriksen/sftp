# ---------------------------------------------------------------------------
# All of these are keyed by storage account sequence_no ("01" = SFTP local
# users, "02" = Entra ID SFTP). They were scalars built with one(values(...))
# while the stack held a single account; that construct errors outright on a
# second account, so consumers index the map instead — see tests/env-test.sh
# and tests/entra/env-entra.sh.
# ---------------------------------------------------------------------------

output "storage_account_ids" {

  description = "Storage account resource ID, keyed by sequence_no. The account name is the last path segment."

  value = { for k, m in module.storage_account : k => m.id }

}

output "local_user_ids" {

  description = "id assigned to each SFTP local user, keyed by sequence_no then sequence_number (0 = inbound, 1 = outbound). Only account \"01\" has local users."

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
# Entra objects backing the account "02" experiment. The object IDs are what
# the named group ACEs in variables.auto.tfvars.json resolve to (via
# local.resolved_storage); the client IDs/secrets are what
# tests/entra/fetch_creds.sh materialises into dotfiles so the harness can
# `az login --service-principal` and mint an OpenSSH certificate per principal.
# ---------------------------------------------------------------------------

output "entra_group_object_ids" {

  description = "Object ID of each created Entra group, keyed by entra_groups[].key."

  value = { for k, g in azuread_group.this : k => g.object_id }

}

output "entra_sp_client_ids" {

  description = "Application (client) ID of each created service principal, keyed by entra_groups[].key."

  value = { for k, a in azuread_application.this : k => a.client_id }

}

output "entra_sp_client_secrets" {

  description = "Client secret for each created service principal, keyed by entra_groups[].key."

  value     = { for k, p in azuread_application_password.this : k => p.value }
  sensitive = true
}
