# ---------------------------------------------------------------------------
# Data-plane RBAC for the storage account in sa.tf.
#
# The Terraform executor needs data-plane rights for module.adls_filesystem
# (storage_use_azuread = true routes those calls through AAD, not a shared
# key). Storage Blob Data Owner is also an ACL superuser, which is what lets
# it write the ACL tree despite every directory above the homes being
# other::--x.
#
# The only other data-plane grants are the container-scoped roles for the
# Entra SFTP principals at the end of this file. Grants are additive and
# can't be narrowed by an ACL, so nothing gets an account-scoped role but the
# executor. (Local users don't interoperate with RBAC at all.)
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

# ---------------------------------------------------------------------------
# Entra SFTP principals (entra.tf): one built-in data-plane role each, scoped
# to a single container -- reader_a gets Storage Blob Data Reader on
# container-a, writer_b Storage Blob Data Contributor on container-b. A
# container-scoped role grants nothing on any other container, which is what
# keeps each principal out of the other's.
#
# Contributor rather than a write-only custom role: Entra SFTP refuses `cd`
# into a directory without read (tested live 2026-10-20 with a -wx ACL), so
# a writer that can navigate has to be able to read.
#
# depends_on module.adls_filesystem because the scope is a container ID built
# by string, which carries no implicit dependency on the container existing.
# ---------------------------------------------------------------------------

resource "azurerm_role_assignment" "entra" {
  for_each = local.entra_principals_map

  scope                = "${module.storage_account[each.value.sequence_no].id}/blobServices/default/containers/${each.value.container}"
  role_definition_name = each.value.role
  principal_id         = azuread_service_principal.this[each.key].object_id
  principal_type       = "ServicePrincipal"

  depends_on = [module.adls_filesystem]
}

# Data-plane role assignments can take minutes to be honoured; without this
# the first test run after an apply can fail on stale authorization.
resource "time_sleep" "entra_rbac_wait" {
  depends_on      = [azurerm_role_assignment.entra]
  create_duration = "120s"
}
