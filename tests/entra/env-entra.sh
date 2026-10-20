# Source env-dev.sh first so ARM_CLIENT_ID / ARM_CLIENT_SECRET are available
# for the admin fixture (Terraform SP has Storage Blob Data Owner).
#
#   source env-dev.sh
#   source tests/entra/env-entra.sh
#   pytest tests/entra/ --confcutdir=tests/entra
#
# Run tests/entra/setup_creds.sh once after apply to create the dotfiles below.

_ENTRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "${_ENTRA_DIR}/../.." && pwd)"

export AZURE_TENANT_ID="$(cat "${_REPO_ROOT}/.tenant_id")"

for _name in reader_a writer_b; do
  _prefix="ENTRA_$(tr '[:lower:]' '[:upper:]' <<<"${_name}")"
  export "${_prefix}_CLIENT_ID=$(cat "${_ENTRA_DIR}/.entra_${_name}_client_id")"
  export "${_prefix}_CLIENT_SECRET=$(cat "${_ENTRA_DIR}/.entra_${_name}_client_secret")"
  export "${_prefix}_KEY_FILE=${_ENTRA_DIR}/.entra_${_name}_key"
done
unset _name _prefix

# Account "02" is the Entra-auth account. Discovered from Terraform state
# rather than hardcoded, so a recreate (the account name is ForceNew) can't
# leave the tests pointed at a stale account.
_SA_ID="$(terraform -chdir="${_REPO_ROOT}" output -json storage_account_ids | jq -er '."02"')"
export ENTRA_STORAGE_ACCOUNT="${_SA_ID##*/}"
