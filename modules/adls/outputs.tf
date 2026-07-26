output "filesystem_ids" {
  value       = { for k, v in azurerm_storage_data_lake_gen2_filesystem.this : k => v.id }
  description = "Map of container name to Data Lake Gen2 filesystem resource ID."
}

output "container_names" {
  # Derived from the filesystem resources (not var.containers) so consumers get
  # an implicit dependency on the containers actually existing, while preserving
  # input order.
  value       = [for c in var.containers : azurerm_storage_data_lake_gen2_filesystem.this[c.container_name].name]
  description = "Names of the created filesystems (containers), in input order."
}

output "path_ids" {
  value       = { for k, v in azurerm_storage_data_lake_gen2_path.this : k => v.id }
  description = "Map of \"<container>::<path>\" to Data Lake Gen2 path resource ID."
}
