# terraform-azurerm-sftp-local-users

Terraform module that creates SFTP local users
(`azurerm_storage_account_local_user`) on an HNS/SFTP-enabled storage account,
with SSH public-key authentication and per-container permission scopes.

`allow_acl_authorization` is applied via `azapi_update_resource` because the
`azurerm` resource does not expose it directly.

Users are keyed by `sequence_number` (0–999) for a stable identity. Extensive
input validation enforces Azure limits (max 1000 users, 100 permission scopes
per user, 10 SSH keys per user) and valid SSH key algorithms and permission
values.

## Usage

```hcl
module "sftp_local_users" {
  source  = "app.terraform.io/leif-lab3/terraform-azurerm-sftp-local-users/azurerm"
  version = "0.1.0"

  storage_account_id = azurerm_storage_account.this.id

  sftp_users = [
    {
      sequence_number = 0
      home_directory  = "silver"
      permission_scopes = [
        { target_container = "silver", permissions = ["Read", "Write", "List"] },
      ]
      ssh_authorized_keys = [
        { key = "ssh-rsa AAAA...", description = "svc key" },
      ]
    },
  ]
}
```

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.3.0 |
| hashicorp/azurerm | >= 4.0.0, < 5.0.0 |
| Azure/azapi | >= 2.0.0, < 3.0.0 |

## Testing

Tests use HCP Terraform as the backend. From the `tests/` directory:

```bash
terraform init
terraform test
```
