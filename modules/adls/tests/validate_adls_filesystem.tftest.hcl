provider "azurerm" {
  features {}
}

run "adls_filesystem" {
  command = plan

  variables {
    storage_account_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa"
    containers = [
      { container_name = "silver" },
      { container_name = "gold" },
    ]
    paths = []
  }

  assert {
    condition     = length(azurerm_storage_data_lake_gen2_filesystem.this) == 2
    error_message = "Expected one filesystem planned per container."
  }
}
