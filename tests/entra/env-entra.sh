# Source env-dev.sh first so ARM_CLIENT_ID / ARM_CLIENT_SECRET are available
# for the admin fixture (Terraform SP has Storage Blob Data Owner).
#
#   source env-dev.sh
#   source tests/entra/env-entra.sh
#   pytest tests/entra/
#
# Run tests/entra/fetch_creds.sh once after apply to create the dotfiles below.

_ENTRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "${_ENTRA_DIR}/../.." && pwd)"

export AZURE_TENANT_ID="$(cat "${_REPO_ROOT}/.tenant_id")"

export ENTRA_READER_CLIENT_ID="$(cat "${_ENTRA_DIR}/.entra_reader_client_id")"
export ENTRA_READER_CLIENT_SECRET="$(cat "${_ENTRA_DIR}/.entra_reader_client_secret")"

export ENTRA_WRITER_CLIENT_ID="$(cat "${_ENTRA_DIR}/.entra_writer_client_id")"
export ENTRA_WRITER_CLIENT_SECRET="$(cat "${_ENTRA_DIR}/.entra_writer_client_secret")"

# Account "02" is the Entra-auth account. Discovered from Terraform state
# rather than hardcoded, so a recreate (the storage account name is ForceNew)
# can't leave the tests silently pointed at a stale account. storage_account_ids
# is a map keyed by sequence_no -- account "01" is the local-user stack.
_SA_ID="$(terraform -chdir="${_REPO_ROOT}" output -json storage_account_ids | jq -er '."02"')"
export ENTRA_STORAGE_ACCOUNT="${_SA_ID##*/}"
