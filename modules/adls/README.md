# terraform-azurerm-adls-filesystem

Terraform module that creates ADLS Gen2 (HNS) filesystems (containers) and
directory paths on a storage account, with optional POSIX ACLs on each.

Each path has a `destroy`-time `local-exec` provisioner that removes the
directory via the `az` CLI (`az storage fs directory delete`), because the
`azurerm` path resource does not always clean up nested directories on destroy.
The execution environment therefore needs the `az` CLI and `bash` available and
authenticated (`--auth-mode login`).

## Usage

```hcl
module "adls_filesystem" {
  source  = "app.terraform.io/leif-lab3/terraform-azurerm-adls-filesystem/azurerm"
  version = "0.1.0"

  storage_account_id = azurerm_storage_account.this.id

  containers = [
    { container_name = "silver" },
    { container_name = "gold" },
  ]

  paths = [
    { container_name = "silver", path_name = "landing" },
  ]
}
```

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.3.0 |
| hashicorp/azurerm | >= 4.0.0, < 5.0.0 |

## Testing

Tests use HCP Terraform as the backend. From the `tests/` directory:

```bash
terraform init
terraform test
```
