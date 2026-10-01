# ---------------------------------------------------------------------------
# Data-plane RBAC for the storage account in sa.tf.
#
# The Terraform executor needs data-plane rights for module.adls_filesystem
# (storage_use_azuread = true routes those calls through AAD, not a shared
# key). Storage Blob Data Owner is also an ACL superuser, which is what lets
# it write the ACL tree despite every directory above the homes being
# other::--x.
#
# Nothing else gets data-plane RBAC: grants are additive and can't be
# narrowed by an ACL, and local users don't interoperate with RBAC anyway.
# ---------------------------------------------------------------------------

resource "azurerm_role_assignment" "tf_executor_blob_owner" {
  for_each = local.storage_map

  scope                = module.storage_account[each.key].id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Role assignments propagate asynchronously; module.adls_filesystem depends on
# this so the first data-plane call after apply doesn't race the grant.
resource "time_sleep" "rbac_wait" {
  depends_on = [
    azurerm_role_assignment.tf_executor_blob_owner,
  ]
  create_duration = "30s"
}
