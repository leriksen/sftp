export env=dev
export TF_VAR_env="${env}"

# The remote backend uses a "sftp-" workspace prefix, so every terraform
# command needs a workspace selected; without it they fail with "default
# workspace not supported". tests/env-test.sh and tests/entra/env-entra.sh both
# shell out to `terraform output`, so this has to be set for them too.
export TF_WORKSPACE="${env}"

export ARM_USE_AZUREAD=true
export ARM_CLIENT_ID="$(cat .client_id_dev)"
export ARM_CLIENT_SECRET="$(cat .key_${env})"
export ARM_SUBSCRIPTION_ID="$(cat .subscription_id)"
export ARM_TENANT_ID="$(cat .tenant_id)"
