variable "storage_account_id" {
  type = string
}

variable "containers" {
  type = list(object({
    container_name = string
    acl = optional(list(object({
      scope       = string
      id          = optional(string)
      permissions = string
      type        = string
    })), [])
  }))
}

variable "paths" {
  type = list(object({
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
}
