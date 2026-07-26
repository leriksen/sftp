output "filesystem_ids" {
  value       = module.adls_filesystem.filesystem_ids
  description = "Map of container name to filesystem resource ID."
}
