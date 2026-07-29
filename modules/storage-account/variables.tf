# ── Required ────────────────────────────────────────────────────────────────

variable "resource_group_name" {
  type        = string
  description = "Resource group to create the storage account and identity in. Also used as the storage account name prefix (\"<resource_group_name>dl<sequence_no>\") when `name` is not set, so it must yield a valid storage account name (3-24 chars, lowercase alphanumeric)."
}

variable "sequence_no" {
  type        = string
  description = "Numeric suffix used to name the user-assigned identity (e.g. \"01\"), and the storage account too when `name` is not set."
}

variable "location" {
  type        = string
  description = "Azure region."
}

# ── Optional ────────────────────────────────────────────────────────────────

variable "name" {
  type        = string
  default     = null
  description = "Explicit storage account name. Local fork of the upstream module: when null (the default), falls back to the upstream naming convention \"<resource_group_name>dl<sequence_no>\". Set this to adopt an existing storage account without a forced replace."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags to apply to the storage account and identity."
}

variable "sftp_enabled" {
  type        = bool
  default     = false
  description = "Enable SFTP and local users on the storage account."
}
