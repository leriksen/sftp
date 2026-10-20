# sftp

Terraform stack and live test suites for comparing the two ways to authenticate to Azure Storage SFTP:

| Account | Name | Authentication | Authorization |
|---|---|---|---|
| `01` | `sftpdl01` | SFTP local users (SSH key) | `other::` ACL entries |
| `02` | `sftpdl02` | Entra ID service principals (OpenSSH certificate) | Container-scoped RBAC |

Both accounts are ADLS Gen2 (hierarchical namespace) in resource group `sftp`, Australia East. They're built from the private-registry modules in `app.terraform.io/leif-lab3` (storage account, ADLS filesystem, SFTP local users).

## Account 01: local users

One container, `sftp-test`, with two local users:

| User | Home |
|---|---|
| `sftpuser0` | `sftp-test/dev01/inbound/sterling` |
| `sftpuser1` | `sftp-test/dev01/outbound/sterling` |

The directories above the homes are `other::--x` (traverse only). The homes are `rwx` with matching default entries.

A local user can only be authorized through `other::`, and every local user shares it. Named user or group ACL entries are rejected for local users (`InvalidNamedUserOrNamedGroup`). As a result, the two users can read and write each other's homes. This is a known, accepted limitation. `tests/test_sftp_overlap.py` asserts it, so it can't be mistaken for isolation.

## Account 02: Entra ID

Local users are disabled on the account (`local_user_enabled = false`). There are two containers, each with one service principal created by `entra.tf`:

| Service principal | Role | Scope | Can |
|---|---|---|---|
| `sftp-entra-reader-a` | Storage Blob Data Reader | `container-a` | list, read, `cd` |
| `sftp-entra-writer-b` | Storage Blob Data Contributor | `container-b` | list, read, create, delete, `cd` |

Neither service principal has any access to the other's container. The container ACLs grant nothing (`other::---`), and no ACL entry names either principal.

Principals, containers and roles are data in `entra_principals` in `variables.auto.tfvars.json`. The role assignments are `azurerm_role_assignment.entra` in `rbac.tf`.

**Authentication.** Nothing is registered on the storage account. Each service principal has its own RSA key pair, kept locally in `tests/entra/.entra_<name>_key` (excluded from git). At test time the principal signs in to Entra, and `az sftp cert` signs its public key into a 65-minute OpenSSH certificate. The login name is `<account>.<principal>`, read from the certificate. Entra principals have no home directory, so every path is container-qualified, for example `/container-a/...`.

**Why the writer has read.** Entra SFTP refuses `cd` into a directory without read permission, even with write and traverse. Default ACL entries apply to files and directories alike, so a writer that can navigate can also read. Container-scoped RBAC is therefore the simplest model. Named-user ACL entries were tried and do work for Entra principals, but they bought nothing over the built-in roles once the writer needed read.

## Prerequisites

- Terraform with a valid Terraform Cloud token in `~/.terraform.d/credentials.tfrc.json`.
- State is in TFC workspace `sftp-dev` (remote execution). `env-dev.sh` sets `TF_WORKSPACE=dev`; without it, commands fail with "default workspace not supported".
- Credential dotfiles at the repo root, read by `env-dev.sh`: `.client_id_dev`, `.key_dev`, `.subscription_id`, `.tenant_id`.
- The Terraform service principal needs:
  - **Azure:** Owner, or rights to create role assignments.
  - **Microsoft Graph:** `Application.ReadWrite.OwnedBy` or broader, admin-consented, for the Entra applications.
- Subscription feature `Microsoft.Storage/SftpEntraIdAccess` registered.
- For the account 01 tests: `.sftp_inbound_key` / `.sftp_outbound_key` at the repo root, matching the public keys in tfvars.
- Azure CLI with the `sftp` extension, plus `jq`, `ssh-keygen` and Python 3.

## Usage

```sh
source env-dev.sh
terraform init
terraform apply

tests/entra/setup_creds.sh   # SP key pairs (once) + client IDs/secrets (after each apply)
tests/run_tests.sh           # both suites; or tests/run_sftp_tests.sh / tests/entra/run_entra_tests.sh

terraform destroy            # SFTP is billed hourly per enabled account
```

The runners create `tests/.venv` and write Markdown, JUnit and HTML reports next to each suite. Use bash: `tests/entra/env-entra.sh` relies on `BASH_SOURCE`.

## Tests

The tests run against real Azure; there are no mocks.

| Suite | Path | Covers |
|---|---|---|
| Local users | `tests/test_sftp_*.py` | home access, traverse-only parents, accepted cross-user overlap |
| Entra identity | `tests/entra/test_entra_identity.py` | each certificate is over that principal's own key; no cross-principal login; bare key refused |
| Entra reader | `tests/entra/test_entra_reader_a.py` | read and list `container-a`; no writes; nothing in `container-b` |
| Entra writer | `tests/entra/test_entra_writer_b.py` | create, delete, `cd`, read and list `container-b`; nothing in `container-a` |

Deny tests only pass on a permission error. A not-found error fails them, so a wrong path can't pass a deny test. Every artifact a test creates is logged to a ledger, and a sweep after each run deletes leftovers from crashed runs, and only those.
