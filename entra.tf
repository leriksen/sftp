# ---------------------------------------------------------------------------
# Entra objects for the storage account "02" experiment: evaluating Azure
# Storage SFTP's Entra ID authentication (GA June 2026) as a replacement for
# the local-user + "other::" ACL scheme account "01" is stuck with.
#
# Account "01"'s design is forced: named user/group ACEs are rejected for
# SFTP *local-user* authorization (InvalidNamedUserOrNamedGroup — see project
# memory sftp-acl-named-user-blocked), leaving "other" as the only ACE class a
# local user can be authorized through, which caps that account at one local
# user per container. Entra principals are authorized through the ordinary
# blob access-control model instead, where named ACEs are the supported path.
#
# One group per role, one service principal in each, and deliberately NO
# data-plane RBAC for either (contrast azurerm_role_assignment.aad_reader /
# .aad_writer in sa.tf, which apply to account "01" only). RBAC grants are
# additive and can't be narrowed by an ACL, so a single Storage Blob Data
# Reader assignment here would mask every ACE this experiment is testing and
# expose the notsftp tree. Group membership is therefore the only thing that
# distinguishes these two principals.
#
# Requires the Terraform SP to hold Microsoft Graph Application.ReadWrite.OwnedBy
# and Group.ReadWrite.All, admin-consented — see the plan's Step 0.
# ---------------------------------------------------------------------------

locals {
  entra_groups_map = { for g in var.entra_groups : g.key => g }
}

resource "azuread_group" "this" {
  for_each = local.entra_groups_map

  display_name     = each.value.display_name
  security_enabled = true

  # The provider SP owns what it creates, which is what makes the narrower
  # Application.ReadWrite.OwnedBy Graph permission sufficient for the apps
  # below; groups need an explicit owner for the same reason.
  owners = [data.azuread_client_config.current.object_id]

  # Membership is managed by azuread_group_member below rather than inline:
  # leaving `members` unset keeps it unmanaged, so a member added out-of-band
  # (e.g. a human added for manual SFTP testing) survives the next apply.
}

resource "azuread_application" "this" {
  for_each = local.entra_groups_map

  display_name = each.value.sp_display_name
  owners       = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "this" {
  for_each = local.entra_groups_map

  client_id = azuread_application.this[each.key].client_id
  owners    = [data.azuread_client_config.current.object_id]
}

# Secret rather than certificate: the test harness authenticates with
# `az login --service-principal -u <client-id> -p <secret>` before minting the
# 65-minute OpenSSH certificate with `az sftp cert`.
resource "azuread_application_password" "this" {
  for_each = local.entra_groups_map

  application_id = azuread_application.this[each.key].id
  display_name   = "sftp-entra-test-harness"
}

resource "azuread_group_member" "this" {
  for_each = local.entra_groups_map

  group_object_id  = azuread_group.this[each.key].object_id
  member_object_id = azuread_service_principal.this[each.key].object_id
}
