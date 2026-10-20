#!/usr/bin/env bash
# One-off setup for the Entra suite, rerunnable at any time.
#
# 1. Generates each service principal's own SSH key pair, if it doesn't exist
#    yet (tests/entra/.entra_<name>_key{,.pub}). RSA only -- Entra does not
#    issue certificates over ECDSA keys. Never regenerated: delete the files
#    to rotate. Nothing is registered in Azure; `az sftp cert` signs the
#    public key at test time.
# 2. Materialises each SP's client ID and secret from Terraform outputs
#    (tests/entra/.entra_<name>_client_{id,secret}). Rerun after any apply
#    that rotates azuread_application_password.this.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENTRA_DIR="$(cd "$(dirname "$0")" && pwd)"

source "$REPO_ROOT/env-dev.sh"

# entra_principals[].key in variables.auto.tfvars.json
NAMES=(reader_a writer_b)

for name in "${NAMES[@]}"; do
  key="$ENTRA_DIR/.entra_${name}_key"
  if [[ ! -f "$key" ]]; then
    ssh-keygen -t rsa -b 4096 -N "" -C "sftp-entra-${name}" -f "$key" -q
    echo "generated $(basename "$key"){,.pub}"
  fi
done

ids="$(terraform -chdir="$REPO_ROOT" output -json entra_sp_client_ids)"
secrets="$(terraform -chdir="$REPO_ROOT" output -json entra_sp_client_secrets)"

for name in "${NAMES[@]}"; do
  umask 077
  jq -er --arg k "$name" '.[$k]' <<<"$ids"     > "$ENTRA_DIR/.entra_${name}_client_id"
  jq -er --arg k "$name" '.[$k]' <<<"$secrets" > "$ENTRA_DIR/.entra_${name}_client_secret"
  echo "wrote .entra_${name}_client_{id,secret}"
done
