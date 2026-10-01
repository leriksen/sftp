# Source env-dev.sh first so ARM_CLIENT_ID / ARM_CLIENT_SECRET are available
# for the admin fixture (Terraform SP has Storage Blob Data Owner).
#
#   source env-dev.sh
#   source tests/env-test.sh
#   pytest tests/

_TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "${_TESTS_DIR}/.." && pwd)"

export AZURE_TENANT_ID="$(cat "${_REPO_ROOT}/.tenant_id")"

# Discovered from Terraform state rather than hardcoded, so a rename/recreate
# of the storage account (name is ForceNew, see modules/storage-account/main.tf)
# can't leave the tests silently pointed at a stale account.
#
# storage_account_ids is keyed by sequence_no; "01" is the only account.
_SA_ID="$(terraform -chdir="${_REPO_ROOT}" output -json storage_account_ids | jq -er '."01"')"
export SFTP_STORAGE_ACCOUNT="${_SA_ID##*/}"

export SFTP_INBOUND_KEY_FILE="${_REPO_ROOT}/.sftp_inbound_key"
export SFTP_OUTBOUND_KEY_FILE="${_REPO_ROOT}/.sftp_outbound_key"
