resource "azurerm_storage_account" "this" {
  name                     = var.storage_account_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true   # ADLS Gen2 — required for SFTP AND ACLs
  sftp_enabled             = true
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_container" "this" {
  for_each              = toset(var.containers)
  name                  = each.value
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_account_local_user" "this" {
  for_each = var.sftp_users
  name                 = each.key
  storage_account_id   = azurerm_storage_account.this.id
  ssh_key_enabled      = each.value.ssh_key != null
  ssh_password_enabled = each.value.ssh_key == null
  home_directory       = each.value.home_directory
  dynamic "ssh_authorized_key" {
    for_each = each.value.ssh_key != null ? [each.value.ssh_key] : []
    content {
      description = "${each.key}-key"
      key         = ssh_authorized_key.value
    }
  }

  # Control-plane: which containers + coarse rights
  dynamic "permission_scope" {
    for_each = each.value.permissions
    content {
      service       = "blob"
      resource_name = permission_scope.value.container
      permissions {
        read   = permission_scope.value.read
        write  = permission_scope.value.write
        list   = permission_scope.value.list
        delete = permission_scope.value.delete
        create = permission_scope.value.create
      }
    }
  }
  depends_on = [azurerm_storage_container.this]
}

# ---------------------------------------------------------------------------

# Data-plane: POSIX ACLs.

# The SFTP local user's SID is exposed as azurerm_storage_account_local_user.sid

# We flatten (user, acl-entry) pairs and set each ACL recursively via az CLI.

# ---------------------------------------------------------------------------

locals {
  # Build one entry per (user, container) with the ACL string to apply.
  acl_entries = flatten([
    for uname, u in var.sftp_users : [
      for acl in u.acls : {
        key           = "${uname}-${acl.container}"
        user          = uname
        container     = acl.container
        path          = acl.path
        # Grant the local user's SID the specified rights; keep default owner/group/other.

        acl_string    = join(",", [
          "user::rwx",
          "group::r-x",
          "other::---",
          "user:${azurerm_storage_account_local_user.this[uname].sid}:${acl.rights}",
          "default:user:${azurerm_storage_account_local_user.this[uname].sid}:${acl.rights}"
        ])
      }
    ]
  ])
}

# allowAclAuthorization is not exposed by the azurerm provider — patch via azapi.
resource "azapi_update_resource" "acl_auth" {
  for_each = { for uname, u in var.sftp_users : uname => u if length(u.acls) > 0 }

  type        = "Microsoft.Storage/storageAccounts/localUsers@2023-05-01"
  resource_id = azurerm_storage_account_local_user.this[each.key].id

  body = {
    properties = {
      allowAclAuthorization = true
    }
  }
}

resource "null_resource" "acls" {
  for_each = { for e in local.acl_entries : e.key => e }

  # Re-run if the ACL string or the target changes
  triggers = {
    acl_string = each.value.acl_string
    path       = each.value.path
    container  = each.value.container
    account    = azurerm_storage_account.this.name
  }

  provisioner "local-exec" {

    interpreter = ["/bin/bash", "-c"] # use ["PowerShell", "-Command"] on Windows agents

    command     = <<-EOT
      az storage fs access set-recursive \
        --account-name "${azurerm_storage_account.this.name}" \
        --file-system "${each.value.container}" \
        --path "${each.value.path}" \
        --acl "${each.value.acl_string}" \
        --auth-mode login
    EOT
  }

  depends_on = [
    azurerm_storage_account_local_user.this,
    azurerm_storage_container.this,
    azapi_update_resource.acl_auth
  ]
}
