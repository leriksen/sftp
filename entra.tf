# ---------------------------------------------------------------------------
# Entra service principals for storage account "02": Azure Storage SFTP with
# Entra ID authentication, no local users at all (local_user_enabled = false).
#
# One service principal per entry in var.entra_principals, each granted one
# container-scoped data-plane role in rbac.tf (azurerm_role_assignment.entra):
#
#   reader_a  Storage Blob Data Reader       on container-a   nothing on container-b
#   writer_b  Storage Blob Data Contributor  on container-b   nothing on container-a
#
# No ACL entry names either principal; the container ACLs only carry
# other::---.
#
# SSH keys are NOT managed here. Entra SFTP authenticates with a short-lived
# OpenSSH certificate that `az sftp cert` mints, signed in as the SP, over a
# public key the client supplies -- nothing is registered on the storage
# account. Each SP's key pair lives locally (tests/entra/setup_creds.sh).
# ---------------------------------------------------------------------------

resource "azuread_application" "this" {
  for_each = local.entra_principals_map

  display_name = each.value.display_name
  owners       = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "this" {
  for_each = local.entra_principals_map

  client_id = azuread_application.this[each.key].client_id
  owners    = [data.azuread_client_config.current.object_id]
}

# Secret rather than certificate: the test harness authenticates with
# `az login --service-principal -u <client-id> -p <secret>` before minting the
# 65-minute OpenSSH certificate with `az sftp cert`.
resource "azuread_application_password" "this" {
  for_each = local.entra_principals_map

  application_id = azuread_application.this[each.key].id
  display_name   = "sftp-entra-test-harness"
}
