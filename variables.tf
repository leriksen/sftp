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
      Omit (null) to track sftp_enabled, which is the module default. Account
      "02" sets it false: it authorizes Entra principals through named group
      ACEs and defines no local users, so leaving the local-user store enabled
      would advertise an authentication path nothing uses. Requires
      storage-account module >= 0.9.0, which decoupled this from sftp_enabled.

    aad_rbac_groups_enabled - Whether to grant var.aad_reader_object_id /
      var.aad_writer_object_id Storage Blob Data Reader / Contributor on this
      account. Only account "01" (the local-user stack) sets this: account
      "02" is deliberately ACL-only, and any data-plane RBAC there would mask
      the named-group ACEs it exists to test (RBAC grants are additive and
      cannot be narrowed by an ACL).

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

    blobs - Fixture files to seed into the containers. Authored here rather
      than in blobs.tf because the two accounts no longer share a layout:
      "01" splits inbound/outbound across two containers (one SFTP local user
      each, the most that design allows), while "02" puts both trees in a
      single container, which is only possible with named-principal ACEs.
      container_name - Container to write into.
      name           - Blob path within the container.
      content        - Literal file content.

    containers - ADLS Gen2 filesystem containers to create.
      container_name - Container name.
      acl            - (optional) List of ACL entries.
        scope       - "access" or "default".
        id          - Object ID of the principal. Literal object IDs only.
        id_ref      - (optional) Key into var.entra_groups, resolved to that
                      group's object ID by local.resolved_storage. Use this
                      instead of `id` for groups this stack creates, whose
                      object IDs aren't knowable at tfvars-authoring time.
        permissions - rwx-style permission string.
        type        - "user", "group", "mask", or "other".

    paths - Directory paths to create within containers.
      container_name - Container the path belongs to.
      path_name      - Path to create (e.g. "dev01").
      resource_type  - (optional) "directory". Default: "directory".
      acl            - (optional) List of ACL entries (same structure as containers.acl).

    ACL SAFETY INVARIANT (local users only): every "other" grant is only safe
    in a container that has exactly one SFTP local user — "other" is shared by
    every local user in a container, so a second user added to an existing
    container would silently inherit that grant too (this is exactly how the
    sibling adls project's push/pull isolation broke). Don't add a second
    SFTP local user to inbound/outbound without revisiting this.

    This invariant does NOT bind account "02", which has no local users and
    authorizes Entra principals through named group ACEs (type = "group" with
    an id). Named ACEs are per-principal, so that account can carry several
    mutually-isolated principals in one container — the thing the local-user
    design can't express, and the reason this experiment exists.
  EOT
  type = list(object({
    sequence_no             = string
    sftp_enabled            = optional(bool, false)
    local_user_enabled      = optional(bool)
    aad_rbac_groups_enabled = optional(bool, false)
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
    blobs = optional(list(object({
      container_name = string
      name           = string
      content        = string
    })), [])
    containers = list(object({
      container_name = string
      acl = optional(list(object({
        scope       = string
        id          = optional(string)
        id_ref      = optional(string)
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
        id_ref      = optional(string)
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

# ---------------------------------------------------------------------------
# Entra groups + service principals created by entra.tf, for the account "02"
# Entra-SFTP experiment. One SP per group so the tests have a credential that
# is a member of exactly one group and nothing else — group membership is the
# only thing distinguishing reader from writer, since neither SP holds any
# data-plane RBAC.
#
# `key` is what containers[].acl / paths[].acl reference via `id_ref`.
# ---------------------------------------------------------------------------
variable "entra_groups" {
  description = "Entra security groups (and a member service principal each) to create for the ACL-only SFTP experiment."
  type = list(object({
    key             = string
    display_name    = string
    sp_display_name = string
  }))
  default = []
}
