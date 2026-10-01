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
}
