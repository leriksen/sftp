resource "azurerm_storage_data_lake_gen2_filesystem" "this" {
  for_each = { for c in var.containers : c.container_name => c }

  name               = each.key
  storage_account_id = var.storage_account_id

  dynamic "ace" {
    for_each = each.value.acl
    content {
      scope       = ace.value.scope
      id          = ace.value.id
      permissions = ace.value.permissions
      type        = ace.value.type
    }
  }
}

resource "azurerm_storage_data_lake_gen2_path" "this" {
  for_each = { for p in var.paths : "${p.container_name}::${p.path_name}" => p }

  path               = each.value.path_name
  filesystem_name    = each.value.container_name
  storage_account_id = var.storage_account_id
  resource           = each.value.resource_type

  dynamic "ace" {
    for_each = each.value.acl
    content {
      scope       = ace.value.scope
      id          = ace.value.id
      permissions = ace.value.permissions
      type        = ace.value.type
    }
  }

  # On destroy, recursively delete the directory (and any data written into it)
  # before the azurerm path delete runs, so the non-recursive azurerm delete does
  # not fail on a non-empty directory (409 "recursive ... must be true"). This is
  # what makes a full teardown one-shot regardless of the order the path
  # instances are destroyed in.
  #
  # Uses the ARM_* service-principal credentials present in the Terraform
  # execution environment (HCP agent or a local `source env-*.sh`) to call the
  # ADLS Gen2 REST API directly — no `az` CLI, which is not available on the HCP
  # remote agent (the previous `az`-based provisioner was a silent no-op there).
  provisioner "local-exec" {
    when        = destroy
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      account=$(printf '%s' "${self.storage_account_id}" | cut -d/ -f9)
      token=$(curl -sS -X POST "https://login.microsoftonline.com/$ARM_TENANT_ID/oauth2/v2.0/token" \
        --data-urlencode "grant_type=client_credentials" \
        --data-urlencode "client_id=$ARM_CLIENT_ID" \
        --data-urlencode "client_secret=$ARM_CLIENT_SECRET" \
        --data-urlencode "scope=https://storage.azure.com/.default" \
        | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
      curl -sS -X DELETE \
        "https://$account.dfs.core.windows.net/${self.filesystem_name}/${self.path}?recursive=true" \
        -H "Authorization: Bearer $token" \
        -H "x-ms-version: 2023-11-03" \
        -o /dev/null -w "recursive-delete ${self.filesystem_name}/${self.path}: HTTP %%{http_code}\n"
    EOT
  }

  depends_on = [azurerm_storage_data_lake_gen2_filesystem.this]
}
