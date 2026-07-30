# ── Required ────────────────────────────────────────────────────────────────

variable "resource_group_name" {
  type        = string
  description = "Resource group the storage account lives in. Not created by this stack — must already exist."
}

variable "location" {
  type        = string
  description = "Azure region."
}

variable "storage" {
  description = <<-EOT
    List of storage accounts to provision (ADLS Gen2 + optional SFTP local
    users), matching the sibling adls project's `storage` variable shape
    (minus the queue/Event Grid/PEP/Snowflake fields this stack has no
    resources for) so the two stacks are directly comparable.

    sequence_no  - Numeric suffix for the storage account name ("<resource_group_name>dl<sequence_no>").
    sftp_enabled - Whether SFTP is enabled on this storage account.

    sftp_users (optional) - SFTP local users to provision. Names are NOT
      settable — terraform-azurerm-sftp-local-users names local users
      "sftpuser<sequence_number>", so the inbound/outbound intent lives in
      home_directory instead of the login name.
      sequence_number         - 0-999, becomes the "sftpuser<N>" login name.
      home_directory          - "<container>/<path>" home directory for the user.
      ssh_key_enabled         - Whether SSH key auth is enabled. Default: true.
      allow_acl_authorization - Default: false.
      permission_scopes       - Container-level permission grants.
        target_container - Container the scope applies to.
        service           - Azure storage service (e.g. "blob").
        permissions       - Allowed operations (e.g. ["Read", "List"]).
      ssh_authorized_keys - SSH public keys to authorise.
        key         - Raw SSH public key string.
        description - Label for the key.

    containers - ADLS Gen2 filesystem containers to create.
      container_name - Container name.
      acl            - (optional) List of ACL entries.
        scope       - "access" or "default".
        id          - Object ID of the principal.
        permissions - rwx-style permission string.
        type        - "user", "group", "mask", or "other".

    paths - Directory paths to create within containers.
      container_name - Container the path belongs to.
      path_name      - Path to create (e.g. "dev01").
      resource_type  - (optional) "directory". Default: "directory".
      acl            - (optional) List of ACL entries (same structure as containers.acl).

    ACL SAFETY INVARIANT: every "other" grant below is only safe in a
    container that has exactly one SFTP local user — "other" is shared by
    every local user in a container, so a second user added to an existing
    container would silently inherit that grant too (this is exactly how the
    sibling adls project's push/pull isolation broke). Don't add a second
    SFTP local user to inbound/outbound without revisiting this.
  EOT
  type = list(object({
    sequence_no  = string
    sftp_enabled = optional(bool, false)
    sftp_users = optional(list(object({
      sequence_number         = number
      home_directory          = string
      ssh_key_enabled         = optional(bool, true)
      allow_acl_authorization = optional(bool, false)
      permission_scopes = optional(list(object({
        target_container = string
        service          = string
        permissions      = list(string)
      })), [])
      ssh_authorized_keys = optional(list(object({
        key         = string
        description = string
      })), [])
    })), [])
    containers = list(object({
      container_name = string
      acl = optional(list(object({
        scope       = string
        id          = optional(string)
        permissions = string
        type        = string
      })), [])
    }))
    paths = list(object({
      container_name = string
      path_name      = string
      resource_type  = optional(string, "directory")
      acl = optional(list(object({
        scope       = string
        id          = optional(string)
        permissions = string
        type        = string
      })), [])
    }))
  }))
}

# ── Optional ────────────────────────────────────────────────────────────────

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
