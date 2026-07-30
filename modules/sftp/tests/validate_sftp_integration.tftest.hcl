# ---------------------------------------------------------------------------
# Integration coverage: chains setup_rg -> setup_storage -> this module with
# command = apply against real Azure resources, proving local users can
# actually be created on a storage account produced by the ported
# app.terraform.io/leif-lab3/terraform-azurerm-storage-account module (see
# setup_storage/main.tf). The validate_sftp_users.tftest.hcl file next to
# this one covers input validation via cheap `plan`-only runs against a
# stubbed storage_account_id instead.
# ---------------------------------------------------------------------------

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
    name     = "tftestsftp"
    location = var.location
  }
}

run "setup_storage" {
  module {
    source = "./setup_storage"
  }
  command = apply

  variables {
    resource_group_name = run.setup_rg.name
    location            = var.location
    sequence_no         = "01"
    container_name      = "sftp"
  }
}

run "sftp_local_users" {
  module {
    source = "./.."
  }
  command = apply

  variables {
    storage_account_id = run.setup_storage.storage_account_id
    sftp_users = [
      {
        sequence_number         = 0
        home_directory          = "${run.setup_storage.container_name}/dev01"
        allow_acl_authorization = true
        permission_scopes       = []
        ssh_authorized_keys = [
          {
            key         = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDIgMlvWyYmt4ehHy7xjKoEbIguVOC+fik8wQpR9T3WC9FRqazQnVy/G0WXdj9uPqZrrgbXJ/6LUHK0ul1uCYG6hF0G2DHCs64F4eBDWXDXSwSjhLxJr6IhZDHCpvW/2J6EX1OWIRU1gpQonWG7kasmQ78sJgLhJGz+aGQeHusY/VsIzhoIp+j50M+8z6u2/FSeFhmOK890bIzQSu932UDjpOnhhrh8DKBVu+V9as4z3rcB8KiwbP18AIy8syEPiBOqyc3MEuNEFMVW3z0GuS/8L4rY6qAIQnyX6bauOmTUesDd6bWHqi6SR2zWac9pWkir+NHeR0Q1GBReV3q4R4BNFTenfIGrsDMiVm9fSvSFc0I8JsEg3Yc5qo5ha3CghdLdkTjlFz3LeKtByOmJ7vfgoRl3UeWY6thHiZzrjZUVIgF7qOfwjEZmxhRqlekvhoDrjtSK7lNy8Nz01ObvJZAtDtbdQcGGpWzZTutItC1b4kzHlmsATXkAPmFCKpPiBr917jxBCY9/62eYnm1av18Sfz7qHmUi49uxkpUniBOljU35bf73AAoiWLBr4/m7nFynFe7fTgtOuDeYVe+mD8efyfuBYyW1PbNdCfmujDNSNIuGpgTlpoPK8mjgdmDHabVs1MxBtpePmeiWaadXLW70PCpvkq9QicXjWSol6PMZww=="
            description = "integration-test-key"
          }
        ]
      }
    ]
  }

  assert {
    condition     = length(output.local_user_ids) == 1
    error_message = "Expected exactly one local user to be created."
  }

  assert {
    condition     = output.local_user_names["0"] == "sftpuser0"
    error_message = "Local user name should follow the sftpuser<sequence_number> convention."
  }
}
