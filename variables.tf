variable "resource_group_name" { type = string }

variable "location" { type = string }

variable "storage_account_name" { type = string }

variable "containers" { type = list(string) }

# Object ID of the AAD group/user used to prove RBAC-based data-plane access
# works independently of (and isn't affected by) the SFTP local-user ACL
# scheme below. Defaults to the same "ADLS_Reader" group used for this in the
# sibling adls project.
variable "aad_reader_object_id" {
  type    = string
  default = "0776fa5b-af57-4808-a1f2-080e5847c806"
}

# Local users, one per container, homed at "<container>/dev01". Names are NOT
# settable — terraform-azurerm-sftp-local-users names local users
# "sftpuser${sequence_number}", so the inbound/outbound intent lives in
# home_directory instead of the login name (same convention the sibling adls
# project already uses).
variable "sftp_users" {
  type = map(object({
    sequence_number = number # 0-999, becomes the "sftpuser<N>" login name
    container       = string # home container; home_directory = "<container>/dev01"
    ssh_key         = optional(string)

    # POSIX rights (rwx form) granted to "other" on this user's home
    # directory (dev01). SAFE ONLY because each container here has exactly
    # one SFTP local user — "other" is shared by every local user in a
    # container, so a second user added to the same container would
    # silently inherit this grant too (this is exactly how the sibling adls
    # project's push/pull isolation broke). Don't add a second SFTP local
    # user to an existing container without revisiting this.
    home_rights = string
  }))
}
