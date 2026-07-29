# terraform-azurerm-storage-account

Vendored copy of [terraform-azurerm-storage-account](https://github.com/leriksen/terraform-azurerm-storage-account)
(also published to the private registry at `app.terraform.io/leif-lab3`), kept
local so the whole `sftp` stack lives in one repo teammates can clone and run
without extra registry/git trips.

Terraform module for an ADLS Gen2 (HNS-enabled) `StorageV2` account with a
dedicated user-assigned managed identity.

The account is created hardened by default: shared access keys disabled, OAuth
default authentication, no public nested items, LRS replication. SFTP and local
users can be enabled via `sftp_enabled`.

The storage account is named `<resource_group_name>dl<sequence_no>` by
default, and the identity `tftest-umi-<sequence_no>`.

**Local fork:** this copy adds a `name` variable (default `null`) not present
upstream, so an existing storage account can be adopted under its real name
without a forced replace (`name` is ForceNew on `azurerm_storage_account`).
When `name` is left unset, behavior matches the published module exactly.

> **Destroy ordering:** the storage account references the identity via
> `identity_ids`, creating an implicit dependency so the account is destroyed
> before the identity. This is intentional for CMK scenarios — see the comment
> in `main.tf`.

## Usage

```hcl
module "storage_account" {
  source = "./modules/storage-account"

  resource_group_name = "myrg"
  sequence_no          = "01"
  location             = "australiaeast"

  tags = {
    environment = "dev"
  }
}
```

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.3.0 |
| hashicorp/azurerm | >= 4.0.0, < 5.0.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| resource\_group\_name | Resource group; also the storage account name prefix when `name` is unset | `string` | — | yes |
| sequence\_no | Numeric suffix for the identity name, and the account name when `name` is unset | `string` | — | yes |
| location | Azure region | `string` | — | yes |
| name | Explicit storage account name override (local fork) | `string` | `null` | no |
| tags | Tags to apply | `map(string)` | `{}` | no |
| sftp\_enabled | Enable SFTP and local users | `bool` | `false` | no |

## Outputs

| Name | Description |
|------|-------------|
| id | Resource ID of the storage account |
| umi\_id | Resource ID of the user-assigned managed identity |
| umi\_principal\_id | Principal ID of the user-assigned managed identity |

## Testing

Tests use HCP Terraform as the backend. From the `tests/` directory:

```bash
terraform init
terraform test
```
