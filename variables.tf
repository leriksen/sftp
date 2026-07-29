# ── Required ────────────────────────────────────────────────────────────────

variable "resource_group_name" {
  type        = string
  description = "Resource group the storage account lives in. Not created by this stack — must already exist."
}

variable "location" {
  type        = string
  description = "Azure region."
}

variable "storage_account_name" {
  type        = string
  description = <<-EOT
    Name of the existing storage account to adopt. Passed through as
    module.storage_account's `name` override (a local fork of the upstream
    terraform-azurerm-storage-account module — see modules/storage-account/README.md)
    so the account keeps this name instead of falling back to the upstream
    naming convention "<resource_group_name>dl<sequence_no>".
  EOT
}

variable "containers" {
  type        = list(string)
  description = "ADLS Gen2 filesystem (container) names to create."
}

variable "sftp_users" {
  description = <<-EOT
    Local users, one per container, homed at "<container>/dev01". Names are NOT
    settable — terraform-azurerm-sftp-local-users names local users
    "sftpuser<sequence_number>", so the inbound/outbound intent lives in
    home_directory instead of the login name (same convention the sibling adls
    project already uses).

    sequence_number     - 0-999, becomes the "sftpuser<N>" login name.
    container           - Home container; home_directory = "<container>/dev01".
    ssh_key             - (optional) SSH public key to authorise.

    home_dir_rights, home_default_rights - POSIX rights (rwx form) granted to
      "other" on this user's home directory (dev01). SAFE ONLY because each
      container here has exactly one SFTP local user — "other" is shared by
      every local user in a container, so a second user added to the same
      container would silently inherit this grant too (this is exactly how the
      sibling adls project's push/pull isolation broke). Don't add a second
      SFTP local user to an existing container without revisiting this.

      home_dir_rights governs dev01 itself (its list/traverse bits);
      home_default_rights is what new children (uploaded files) inherit as
      their own access ACL. These differ for inbound: `r` on the directory
      lets it list its own home dir, but omitting `r` from the default keeps
      the files it uploads unreadable by inbound itself.
  EOT
  type = map(object({
    sequence_number     = number
    container           = string
    ssh_key             = optional(string)
    home_dir_rights     = string
    home_default_rights = string
  }))
}

# ── Optional ────────────────────────────────────────────────────────────────

variable "storage_account_sequence_no" {
  type        = string
  default     = "01"
  description = "Only used to name module.storage_account's user-assigned identity (\"tftest-umi-<sequence_no>\") — the storage account name itself is set explicitly via storage_account_name above, not derived from this."
}

# Object IDs of the AAD groups used to prove RBAC-based data-plane access
# works independently of (and isn't affected by) the SFTP local-user ACL
# scheme below. Default to the same "ADLS_Reader" / "ADLS_Write" groups used
# for this in the sibling adls project.
variable "aad_reader_object_id" {
  type    = string
  default = "0776fa5b-af57-4808-a1f2-080e5847c806"
}

variable "aad_writer_object_id" {
  type    = string
  default = "39ed111b-231e-4f6f-9371-5c0a64a029ad"
}
