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
