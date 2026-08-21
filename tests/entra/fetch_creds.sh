#!/usr/bin/env bash
# Materialise the Entra test service principals' credentials from Terraform
# outputs into dotfiles, following the same convention as the hand-created
# tests/.aad_* files. Unlike those, these principals are Terraform-managed, so
# there is nothing to copy by hand -- rerun this after any apply that rotates
# azuread_application_password.this.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENTRA_DIR="$(cd "$(dirname "$0")" && pwd)"

ids="$(terraform -chdir="$REPO_ROOT" output -json entra_sp_client_ids)"
secrets="$(terraform -chdir="$REPO_ROOT" output -json entra_sp_client_secrets)"

for role in reader writer; do
  key="${role}s"   # entra_groups[].key is plural: readers / writers
  jq -er --arg k "$key" '.[$k]' <<<"$ids"     > "$ENTRA_DIR/.entra_${role}_client_id"
  jq -er --arg k "$key" '.[$k]' <<<"$secrets" > "$ENTRA_DIR/.entra_${role}_client_secret"
  chmod 600 "$ENTRA_DIR/.entra_${role}_client_id" "$ENTRA_DIR/.entra_${role}_client_secret"
  echo "wrote .entra_${role}_client_{id,secret}"
done
