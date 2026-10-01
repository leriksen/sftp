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
  version  = "0.10.0"
  for_each = local.storage_map

  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sequence_no         = each.key
  sftp_enabled        = each.value.sftp_enabled
  local_user_enabled  = each.value.local_user_enabled
}

# ---------------------------------------------------------------------------
# Containers + POSIX ACL tree, via the published terraform-azurerm-adls-filesystem
# module (github.com/leriksen/terraform-azurerm-adls-filesystem) — sourced from
# the private registry at app.terraform.io/leif-lab3, same module and version
# pin the sibling adls project uses. containers/paths are passed straight
# through from var.storage as data (same as adls's sa.tf) — every ACL block is
# authored directly in variables.auto.tfvars.json, not derived here.
#
# Every ACE is `type = "other"` with no `id`: that is the only ACE class an
# SFTP *local user* can be authorized through (named user/group ACEs are
# rejected for local-user authorization, InvalidNamedUserOrNamedGroup — see
# project memory sftp_acl_named_user_blocked).
#
# Layout (single container "sftp-test"):
#   /                        other::--x                 traverse only
#   dev01                    other::--x                 traverse only
#   dev01/{inbound,outbound} other::--x                 traverse only
#   dev01/*/sterling         user::rwx  other::rwx      home dirs
#                            default:user::rwx default:other::rwx
# The default entries make every file/dir a user creates under its home
# inherit rwx, so nested directories work at any depth. user:: matters
# because Azure makes the uploading local user ("lu-<userId>") the owner.
#
# KNOWN, ACCEPTED OVERLAP: other:: is shared by every local user on the
# account, so both users get rwx on BOTH sterling dirs — each can create,
# read and delete in the other's home. Local users can't be isolated within
# one container; isolation needs one container per user, or Entra principals
# with named ACEs. tests/ asserts the overlap explicitly so it can't be
# mistaken for isolation.
#
# Setting the ACL directly on the azurerm_storage_data_lake_gen2_filesystem
# resource (via containers[].acl) is what makes the container-root ACL work
# at all: a separate azurerm_storage_data_lake_gen2_path with path = ""
# fails with "resource already exists".
# ---------------------------------------------------------------------------

module "adls_filesystem" {
  source   = "app.terraform.io/leif-lab3/terraform-azurerm-adls-filesystem/azurerm"
  version  = "0.3.0"
  for_each = local.storage_map

  storage_account_id = module.storage_account[each.key].id
  containers         = each.value.containers
  paths              = each.value.paths

  depends_on = [time_sleep.rbac_wait]
}
