# ── Required ────────────────────────────────────────────────────────────────

variable "resource_group_name" {
  type        = string
  description = "Resource group the storage account lives in. Created by this stack (rg.tf)."
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

    local_user_enabled - Whether local users are enabled on the account.
      Omit (null) to track sftp_enabled, which is the module default.
      Requires storage-account module >= 0.9.0, which decoupled this from
      sftp_enabled.

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
        id          - Object ID of the principal (named entries only).
        permissions - rwx-style permission string.
        type        - "user", "group", "mask", or "other".

    paths - Directory paths to create within containers.
      container_name - Container the path belongs to.
      path_name      - Path to create (e.g. "dev01").
      resource_type  - (optional) "directory". Default: "directory".
      acl            - (optional) List of ACL entries (same structure as containers.acl).

    ACL OVERLAP (local users only): local users can only be authorized
    through "other" ACEs, and "other" is shared by every local user on the
    account. Any grant made for one user's home applies equally to every
    other local user, so users in one container are NOT isolated from each
    other. This is a known, accepted property of the current layout -- see
    sa.tf.
  EOT
  type = list(object({
    sequence_no        = string
    sftp_enabled       = optional(bool, false)
    local_user_enabled = optional(bool)
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
