locals {
  # ---------------------------------------------------------------------------
  # storage_map: var.storage list → map keyed by sequence_no (as string).
  # Mirrors the sibling adls project's local of the same name.
  # ---------------------------------------------------------------------------
  storage_map = { for sa in var.storage : sa.sequence_no => sa }

  # ---------------------------------------------------------------------------
  # sftp_configs: SA key → resolved sftp_users list, for SAs that have SFTP
  # enabled and at least one user defined. Values already match
  # module.sftp_local_users' `sftp_users` argument shape one-to-one, so no
  # transformation is needed (unlike the adls project's equivalent local,
  # which additionally reads SSH keys from disk via file() — this stack
  # keeps keys inline in tfvars).
  # ---------------------------------------------------------------------------
  sftp_configs = {
    for sa in var.storage : sa.sequence_no => sa.sftp_users
    if sa.sftp_enabled && length(sa.sftp_users) > 0
  }

  # ---------------------------------------------------------------------------
  # all_container_names: every container name across all storage accounts,
  # for blobs.tf's for_each = toset(...) fixture-blob loops.
  # ---------------------------------------------------------------------------
  all_container_names = toset(flatten([
    for sa in var.storage : [for c in sa.containers : c.container_name]
  ]))

  # ---------------------------------------------------------------------------
  # container_arm_ids: classic ARM resource ID per container
  # (".../blobServices/default/containers/<name>"), built directly since
  # azurerm_storage_blob needs this form rather than the DFS URL that
  # module.adls_filesystem.filesystem_ids returns. Flattened across all
  # storage accounts so it stays correct regardless of account count.
  # ---------------------------------------------------------------------------
  container_arm_ids = {
    for pair in flatten([
      for sa_key, sa in local.storage_map : [
        for c in sa.containers : {
          container_name = c.container_name
          arm_id         = "${module.storage_account[sa_key].id}/blobServices/default/containers/${c.container_name}"
        }
      ]
    ]) : pair.container_name => pair.arm_id
  }
}
