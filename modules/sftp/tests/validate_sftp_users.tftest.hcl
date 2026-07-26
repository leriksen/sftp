provider "azurerm" {
  features {}
}

# ── SSH key type validation ───────────────────────────────────────────────────

run "reject_ssh_dss_key" {
  module {
    source = "./.."
  }
  command = plan

  variables {
    storage_account_id = "stub"
    sftp_users = [
      {
        sequence_number   = 0
        home_directory    = "/sftphome/user0"
        permission_scopes = []
        ssh_authorized_keys = [
          {
            key         = "ssh-dss AAAAB3NzaC1kc3MAAACBAKtestfakekey description=test"
            description = "dss key — not an allowed type"
          }
        ]
      }
    ]
  }

  expect_failures = [var.sftp_users]
}

run "reject_ed25519_key" {
  module {
    source = "./.."
  }
  command = plan

  variables {
    storage_account_id = "stub"
    sftp_users = [
      {
        sequence_number   = 0
        home_directory    = "/sftphome/user0"
        permission_scopes = []
        ssh_authorized_keys = [
          {
            key         = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItestfakekey"
            description = "ed25519 key — not an allowed type"
          }
        ]
      }
    ]
  }

  expect_failures = [var.sftp_users]
}

run "reject_fido2_key" {
  module {
    source = "./.."
  }
  command = plan

  variables {
    storage_account_id = "stub"
    sftp_users = [
      {
        sequence_number   = 0
        home_directory    = "/sftphome/user0"
        permission_scopes = []
        ssh_authorized_keys = [
          {
            key         = "sk-ssh-ed25519@openssh.com AAAAGnNrLXNzaC1lZDI1NTE5testfakekey"
            description = "fido2 ed25519 key — not an allowed type"
          }
        ]
      }
    ]
  }

  expect_failures = [var.sftp_users]
}

run "reject_invalid_prefix" {
  module {
    source = "./.."
  }
  command = plan

  variables {
    storage_account_id = "stub"
    sftp_users = [
      {
        sequence_number   = 0
        home_directory    = "/sftphome/user0"
        permission_scopes = []
        ssh_authorized_keys = [
          {
            key         = "not-a-valid-key-type AAAA..."
            description = "completely invalid key prefix"
          }
        ]
      }
    ]
  }

  expect_failures = [var.sftp_users]
}

run "reject_mixed_valid_and_invalid_keys" {
  module {
    source = "./.."
  }
  command = plan

  variables {
    storage_account_id = "stub"
    sftp_users = [
      {
        sequence_number   = 0
        home_directory    = "/sftphome/user0"
        permission_scopes = []
        ssh_authorized_keys = [
          {
            key         = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCtestfakekey"
            description = "valid rsa key"
          },
          {
            key         = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItestfakekey"
            description = "invalid ed25519 — should cause the whole user entry to be rejected"
          }
        ]
      }
    ]
  }

  expect_failures = [var.sftp_users]
}
