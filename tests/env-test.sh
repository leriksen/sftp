# Source env-dev.sh first so ARM_CLIENT_ID / ARM_CLIENT_SECRET are available
# for the admin fixture (Terraform SP has Storage Blob Data Owner).
#
#   source env-dev.sh
#   source tests/env-test.sh
#   pytest tests/

_TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "${_TESTS_DIR}/.." && pwd)"

export AZURE_TENANT_ID="$(cat "${_REPO_ROOT}/.tenant_id")"

export AAD_READER_CLIENT_ID="$(cat "${_TESTS_DIR}/.aad_reader_client_id")"
export AAD_READER_CLIENT_SECRET="$(cat "${_TESTS_DIR}/.aad_reader_client_secret")"

export AAD_WRITER_CLIENT_ID="$(cat "${_TESTS_DIR}/.aad_writer_client_id")"
export AAD_WRITER_CLIENT_SECRET="$(cat "${_TESTS_DIR}/.aad_writer_client_secret")"

# Discovered from Terraform state rather than hardcoded, so a rename/recreate
# of the storage account (name is ForceNew, see modules/storage-account/main.tf)
# can't leave the tests silently pointed at a stale account.
_SA_ID="$(terraform -chdir="${_REPO_ROOT}" output -raw storage_account_id)"
export SFTP_STORAGE_ACCOUNT="${_SA_ID##*/}"

export SFTP_INBOUND_KEY_FILE="${_REPO_ROOT}/.sftp_inbound_key"
export SFTP_OUTBOUND_KEY_FILE="${_REPO_ROOT}/.sftp_outbound_key"
