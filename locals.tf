locals {
  # ---------------------------------------------------------------------------
  # notsftp_deny_acl: explicit deny ACL applied to the "notsftp" / "notsftp/private"
  # tree in each container, independent of whatever the container root ends up
  # granting.
  # ---------------------------------------------------------------------------
  notsftp_deny_acl = [
    { scope = "access", id = null, type = "other", permissions = "---" },
    { scope = "default", id = null, type = "other", permissions = "---" },
  ]

  # ---------------------------------------------------------------------------
  # container_arm_ids: classic ARM resource ID per container
  # (".../blobServices/default/containers/<name>"), built directly since
  # azurerm_storage_blob needs this form rather than the DFS URL that
  # module.adls_filesystem.filesystem_ids returns.
  # ---------------------------------------------------------------------------
  container_arm_ids = {
    for c in var.containers : c => "${module.storage_account.id}/blobServices/default/containers/${c}"
  }
}
