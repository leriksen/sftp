# ---------------------------------------------------------------------------
# SFTP local users, via the published terraform-azurerm-sftp-local-users
# module (github.com/leriksen/terraform-azurerm-sftp-local-users) — sourced
# from the private registry at app.terraform.io/leif-lab3, same module and
# version pin the sibling adls project uses. Names aren't settable — the
# module names local users "sftpuser<sequence_number>" — so the
# inbound/outbound intent lives in home_directory instead of the login name
# (same convention the sibling adls project already uses).
#
# No container-level permission_scopes at all: Microsoft's docs guarantee a
# connection succeeds as long as the user has ACL permission to their home
# directory ("the local user must have at least one container permission OR
# ACL permission to the home directory ... otherwise the connection
# fails") — which module.adls_filesystem's dev01 ACL provides. Any
# container-level grant (even just List) applies account-wide across the
# whole container and would bypass the notsftp deny ACL entirely, per the
# live-test finding above.
#
# local.sftp_configs values already match this module's `sftp_users` argument
# shape one-to-one (unlike adls, which reads SSH keys from disk via file() —
# this stack keeps keys inline in tfvars), so each.value is passed straight
# through.
# ---------------------------------------------------------------------------

module "sftp_local_users" {
  source   = "app.terraform.io/leif-lab3/terraform-azurerm-sftp-local-users/azurerm"
  version  = "0.1.0"
  for_each = local.sftp_configs

  storage_account_id = module.storage_account[each.key].id
  sftp_users         = each.value

  depends_on = [module.adls_filesystem]
}
