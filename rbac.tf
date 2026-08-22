# ---------------------------------------------------------------------------
# Data-plane RBAC for the storage accounts in sa.tf.
#
# The Terraform executor needs data-plane rights for module.adls_filesystem
# (storage_use_azuread = true routes those calls through AAD, not a shared
# key), on every account. Storage Blob Data Owner is also what lets it write
# ACLs on account "02" despite that account's container roots being
# other::--- — the role is an ACL superuser.
#
# The two aad_* assignments grant two real AAD groups (reused from the adls
# project: "ADLS_Reader" / "ADLS_Write") Storage Blob Data Reader /
# Contributor, so tests can prove RBAC-based access works independently of —
# and isn't affected by — the SFTP local-user ACL scheme (local users do not
# interoperate with RBAC). Verified empirically before adding: the reader
# group's test SP already had working read access via ADLS_Reader; the
# writer group's test SP had none (403 AuthorizationPermissionMismatch)
# until this aad_writer assignment was added.
#
# They are scoped to accounts opting in via aad_rbac_groups_enabled, i.e.
# account "01" only — see local.aad_rbac_accounts in locals.tf. Account "02"
# must stay free of data-plane RBAC: role assignments are additive and cannot
# be narrowed by an ACL, so a single Reader grant there would mask every
# named-group ACE the Entra experiment tests and would expose its notsftp
# tree.
# ---------------------------------------------------------------------------

resource "azurerm_role_assignment" "tf_executor_blob_owner" {
  for_each = local.storage_map

  scope                = module.storage_account[each.key].id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "aad_reader" {
  for_each = local.aad_rbac_accounts

  scope                = module.storage_account[each.key].id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = var.aad_reader_object_id
  principal_type       = "Group"
}

resource "azurerm_role_assignment" "aad_writer" {
  for_each = local.aad_rbac_accounts

  scope                = module.storage_account[each.key].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.aad_writer_object_id
  principal_type       = "Group"
}

# Role assignments propagate asynchronously; module.adls_filesystem depends on
# this so the first data-plane call after apply doesn't race the grant.
resource "time_sleep" "rbac_wait" {
  depends_on = [
    azurerm_role_assignment.tf_executor_blob_owner,
    azurerm_role_assignment.aad_reader,
    azurerm_role_assignment.aad_writer,
  ]
  create_duration = "30s"
}
