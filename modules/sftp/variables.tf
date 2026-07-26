# ── Required ────────────────────────────────────────────────────────────────

variable "storage_account_id" {
  type        = string
  description = "Resource ID of the Storage Account to create local SFTP users within."
}

# ── Users ────────────────────────────────────────────────────────────────────

variable "sftp_users" {
  type = list(object({
    sequence_number         = number
    home_directory          = string
    ssh_key_enabled         = optional(bool, true)
    allow_acl_authorization = optional(bool, false)
    permission_scopes = list(object({
      target_container = string
      service          = optional(string, "blob")
      permissions      = optional(list(string), [])
    }))
    ssh_authorized_keys = list(object({
      key         = string
      description = optional(string)
    }))
  }))
  default     = []
  description = "List of SFTP local users. Maximum 1000 entries; sequence_number (0–999) is used as the stable map key."

  validation {
    condition     = length(var.sftp_users) <= 1000
    error_message = "sftp_users may contain at most 1000 entries."
  }

  validation {
    condition     = alltrue([for u in var.sftp_users : u.sequence_number >= 0 && u.sequence_number <= 999])
    error_message = "sequence_number must be between 0 and 999 (inclusive)."
  }

  validation {
    condition     = length(distinct([for u in var.sftp_users : u.sequence_number])) == length(var.sftp_users)
    error_message = "sequence_number must be unique across all sftp_users."
  }

  validation {
    condition     = alltrue([for u in var.sftp_users : length(u.permission_scopes) <= 100])
    error_message = "permission_scopes may contain at most 100 entries per user."
  }

  validation {
    condition     = alltrue([for u in var.sftp_users : length(u.ssh_authorized_keys) <= 10])
    error_message = "ssh_authorized_keys may contain at most 10 entries per user."
  }

  validation {
    condition = alltrue([
      for u in var.sftp_users : alltrue([
        for k in u.ssh_authorized_keys : anytrue([
          for prefix in ["ssh-rsa", "rsa-sha2-256", "rsa-sha2-512", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521"] : startswith(k.key, prefix)
        ])
      ])
    ])
    error_message = "Each ssh_authorized_key must begin with one of: ssh-rsa, rsa-sha2-256, rsa-sha2-512, ecdsa-sha2-nistp256, ecdsa-sha2-nistp384, ecdsa-sha2-nistp521."
  }

  validation {
    condition = alltrue([
      for u in var.sftp_users : alltrue([
        for s in u.permission_scopes : alltrue([
          for p in s.permissions : contains(["All", "Create", "Delete", "List", "Read", "Write"], p)
        ])
      ])
    ])
    error_message = "permissions values must be one of: All, Create, Delete, List, Read, Write."
  }
}
