# ---------------------------------------------------------------------------
# Storage accounts, via the published terraform-azurerm-storage-account module
# (github.com/leriksen/terraform-azurerm-storage-account) — sourced from the
# private registry at app.terraform.io/leif-lab3, same as module.adls_filesystem
# and module.sftp_local_users below, same module/version pin the sibling adls
# project uses. for_each over local.storage_map mirrors adls's sa.tf even
# though this stack only ever has one entry, so the two stacks stay directly
# comparable.
# ---------------------------------------------------------------------------
module "storage_account" {
  source   = "app.terraform.io/leif-lab3/terraform-azurerm-storage-account/azurerm"
  version  = "0.9.1"
  for_each = local.storage_map

  resource_group_name = var.resource_group_name
  location            = var.location
  sequence_no         = each.key
  sftp_enabled        = each.value.sftp_enabled
  local_user_enabled  = each.value.local_user_enabled
}

# ---------------------------------------------------------------------------
# RBAC: the Terraform executor needs data-plane rights for module.adls_filesystem
# below (storage_use_azuread = true routes those calls through AAD, not a
# shared key), on every account. Storage Blob Data Owner is also what lets it
# write ACLs on account "02" despite that account's container roots being
# other::--- — the role is an ACL superuser.
#
# The two aad_* assignments below grant two real AAD groups (reused from the
# adls project: "ADLS_Reader" / "ADLS_Write") Storage Blob Data Reader /
# Contributor, so tests can prove RBAC-based access works independently of —
# and isn't affected by — the SFTP local-user ACL scheme (local users do not
# interoperate with RBAC). Verified empirically before adding: the reader
# group's test SP already had working read access via ADLS_Reader; the
# writer group's test SP had none (403 AuthorizationPermissionMismatch)
# until this aad_writer assignment was added.
#
# They are scoped to accounts opting in via aad_rbac_groups_enabled, i.e.
# account "01" only. Account "02" must stay free of data-plane RBAC: role
# assignments are additive and cannot be narrowed by an ACL, so a single
# Reader grant there would mask every named-group ACE the Entra experiment
# tests and would expose its notsftp tree.
# ---------------------------------------------------------------------------

locals {
  aad_rbac_accounts = {
    for k, sa in local.storage_map : k => sa if sa.aad_rbac_groups_enabled
  }
}

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

resource "time_sleep" "rbac_wait" {
  depends_on = [
    azurerm_role_assignment.tf_executor_blob_owner,
    azurerm_role_assignment.aad_reader,
    azurerm_role_assignment.aad_writer,
  ]
  create_duration = "30s"
}

# ---------------------------------------------------------------------------
# Containers + POSIX ACL tree, via the published terraform-azurerm-adls-filesystem
# module (github.com/leriksen/terraform-azurerm-adls-filesystem) — sourced from
# the private registry at app.terraform.io/leif-lab3, same module and version
# pin the sibling adls project uses. containers/paths are passed straight
# through from var.storage as data (same as adls's sa.tf) — every ACL block
# (including the notsftp deny tree and the outbound sample fixtures) is
# authored directly in variables.auto.tfvars.json, not derived here. Its
# `acl` blocks map straight onto azurerm_storage_data_lake_gen2_filesystem/_path
# `ace` blocks. Account "01" uses `type = "other"` with no `id` — the only ACE
# type an SFTP *local user* can ever be authorized through (named user/group
# ACEs are rejected for local-user authorization, InvalidNamedUserOrNamedGroup
# — see project memory sftp_acl_named_user_blocked). Account "02" has no local
# users and uses `type = "group"` with an `id`, which is the supported path for
# Entra principals; tfvars writes those as `id_ref` keys and local.resolved_storage
# substitutes the object IDs entra.tf created.
#
# Setting the ACL directly on the azurerm_storage_data_lake_gen2_filesystem
# resource (via containers[].acl) is what makes the container-root ACL work
# at all: a separate azurerm_storage_data_lake_gen2_path with path = ""
# fails with "resource already exists" (the filesystem root always
# implicitly exists the moment the container does, and that resource's
# create-only semantics can't adopt it without a manual `terraform import`).
#
# ACL SAFETY INVARIANT (see variables.tf): every "other" grant in tfvars is
# only safe in a container with exactly one SFTP local user. Don't add a
# second SFTP local user to inbound/outbound without revisiting the ACL data.
# Account "02" is exempt — named group ACEs are per-principal, so it can carry
# several mutually-isolated principals in one container.
# ---------------------------------------------------------------------------

module "adls_filesystem" {
  source   = "app.terraform.io/leif-lab3/terraform-azurerm-adls-filesystem/azurerm"
  version  = "0.3.0"
  for_each = local.storage_map

  storage_account_id = module.storage_account[each.key].id
  containers         = local.resolved_storage[each.key].containers
  paths              = local.resolved_storage[each.key].paths

  depends_on = [
    azurerm_role_assignment.tf_executor_blob_owner,
    azurerm_role_assignment.aad_reader,
    time_sleep.rbac_wait,
    # Named group ACEs reference groups by object ID; the membership must
    # exist before the ACEs land or the first access check after apply can
    # race the directory.
    azuread_group_member.this,
  ]
}
