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
# fails") — which module.adls_filesystem's dev01 ACL above provides. Any
# container-level grant (even just List) applies account-wide across the
# whole container and would bypass the notsftp deny ACL entirely, per the
# live-test finding above.
# ---------------------------------------------------------------------------

module "sftp_local_users" {
  source  = "app.terraform.io/leif-lab3/terraform-azurerm-sftp-local-users/azurerm"
  version = "0.1.0"

  storage_account_id = module.storage_account.id

  sftp_users = [
    for uname, u in var.sftp_users : {
      sequence_number         = u.sequence_number
      home_directory          = "${u.container}/dev01"
      allow_acl_authorization = true
      permission_scopes       = []
      ssh_authorized_keys = u.ssh_key != null ? [
        { key = u.ssh_key, description = "${uname}-key" }
      ] : []
    }
  ]

  depends_on = [module.adls_filesystem]
}
