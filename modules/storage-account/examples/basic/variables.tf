# ── Required ────────────────────────────────────────────────────────────────

variable "resource_group_name" {
  type        = string
  description = "Resource group; also the storage account name prefix."
}

variable "location" {
  type        = string
  description = "Azure region."
  default     = "australiaeast"
}
