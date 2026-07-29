provider "azurerm" {
  features {}
}

variables {
  location = "australiaeast"
}

run "setup_rg" {
  module {
    source = "./setup_rg"
  }
  command = apply

  variables {
    name     = "tftestsa"
    location = var.location
  }
}

run "storage_account" {
  module {
    source = "./.."
  }
  command = apply

  variables {
    resource_group_name = run.setup_rg.name
    location            = var.location
    sequence_no         = "01"
    tags                = { env = "tftest" }
  }

  assert {
    condition     = azurerm_storage_account.this.name == "tftestsadl01"
    error_message = "Storage account name should be <resource_group_name>dl<sequence_no>."
  }

  assert {
    condition     = azurerm_storage_account.this.is_hns_enabled == true
    error_message = "Storage account must have HNS (ADLS Gen2) enabled."
  }

  assert {
    condition     = output.umi_principal_id != ""
    error_message = "UMI principal id should be set."
  }
}
