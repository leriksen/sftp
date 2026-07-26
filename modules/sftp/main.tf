resource "azurerm_storage_account_local_user" "this" {
  for_each = local.users_by_sequence

  name                 = "sftpuser${each.key}"
  storage_account_id   = var.storage_account_id
  home_directory       = each.value.home_directory
  ssh_key_enabled      = each.value.ssh_key_enabled
  ssh_password_enabled = false

  dynamic "permission_scope" {
    for_each = each.value.permission_scopes
    content {
      resource_name = permission_scope.value.target_container
      service       = permission_scope.value.service

      permissions {
        create = contains(permission_scope.value.permissions, "All") || contains(permission_scope.value.permissions, "Create")
        delete = contains(permission_scope.value.permissions, "All") || contains(permission_scope.value.permissions, "Delete")
        list   = contains(permission_scope.value.permissions, "All") || contains(permission_scope.value.permissions, "List")
        read   = contains(permission_scope.value.permissions, "All") || contains(permission_scope.value.permissions, "Read")
        write  = contains(permission_scope.value.permissions, "All") || contains(permission_scope.value.permissions, "Write")
      }
    }
  }

  dynamic "ssh_authorized_key" {
    for_each = each.value.ssh_authorized_keys
    content {
      key         = ssh_authorized_key.value.key
      description = ssh_authorized_key.value.description
    }
  }
}

# allowAclAuthorization is not exposed by the azurerm provider — patch via azapi.
resource "azapi_update_resource" "acl_auth" {
  for_each = local.users_by_sequence

  type        = "Microsoft.Storage/storageAccounts/localUsers@2023-05-01"
  resource_id = azurerm_storage_account_local_user.this[each.key].id

  body = {
    properties = {
      allowAclAuthorization = each.value.allow_acl_authorization
    }
  }
}
