variable "resource_group_name"  { type = string }

variable "location"             { type = string }

variable "storage_account_name" { type = string }

variable "containers"           { type = list(string) }

variable "sftp_users" {
  type = map(object({
    home_directory = string
    ssh_key        = optional(string)    # Control-plane permission scopes
    permissions = list(object({
      container = string
      read      = optional(bool, true)
      write     = optional(bool, true)
      list      = optional(bool, true)
      delete    = optional(bool, false)
      create    = optional(bool, true)
    }))
    # Data-plane POSIX ACLs
    acls = optional(list(object({
      container = string
      path      = optional(string, "/")   # directory to apply ACL to (recursive)
      rights    = optional(string, "rwx") # POSIX rights for this user's SID: r/w/x
    })), [])
  }))
}
