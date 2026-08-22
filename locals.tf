locals {
  # ---------------------------------------------------------------------------
  # storage_map: var.storage list → map keyed by sequence_no (as string).
  # Mirrors the sibling adls project's local of the same name.
  # ---------------------------------------------------------------------------
  storage_map = { for sa in var.storage : sa.sequence_no => sa }

  # ---------------------------------------------------------------------------
  # aad_rbac_accounts: the subset of storage_map opting into the data-plane
  # RBAC group grants in rbac.tf, i.e. account "01" only. Account "02" must
  # stay free of data-plane RBAC: role assignments are additive and cannot be
  # narrowed by an ACL, so a single Reader grant there would mask every
  # named-group ACE the Entra experiment tests.
  # ---------------------------------------------------------------------------
  aad_rbac_accounts = {
    for k, sa in local.storage_map : k => sa if sa.aad_rbac_groups_enabled
  }

  # ---------------------------------------------------------------------------
  # sftp_configs: SA key → resolved sftp_users list, for SAs that have SFTP
  # enabled and at least one user defined. Values already match
  # module.sftp_local_users' `sftp_users` argument shape one-to-one, so no
  # transformation is needed (unlike the adls project's equivalent local,
  # which additionally reads SSH keys from disk via file() — this stack
  # keeps keys inline in tfvars).
  # ---------------------------------------------------------------------------
  sftp_configs = {
    for sa in var.storage : sa.sequence_no => sa.sftp_users
    if sa.sftp_enabled && length(sa.sftp_users) > 0
  }

  # ---------------------------------------------------------------------------
  # all_containers: every (storage account, container) pair, keyed
  # "<sa_key>::<container_name>", the index for local.container_arm_ids. Keyed
  # by the pair rather than the container name alone because container names
  # are only unique within an account — keying on name would collapse two
  # accounts' same-named containers onto one ARM ID.
  # ---------------------------------------------------------------------------
  all_containers = {
    for pair in flatten([
      for sa_key, sa in local.storage_map : [
        for c in sa.containers : {
          key            = "${sa_key}::${c.container_name}"
          sa_key         = sa_key
          container_name = c.container_name
        }
      ]
    ]) : pair.key => pair
  }

  # ---------------------------------------------------------------------------
  # all_blobs: every fixture blob across every account, keyed
  # "<sa_key>::<container_name>::<name>". Flattened from each account's own
  # `blobs` list rather than derived from the container set, because the two
  # accounts place the same fixtures at different container-relative paths
  # (account "02" nests both trees under one container).
  # ---------------------------------------------------------------------------
  all_blobs = {
    for b in flatten([
      for sa_key, sa in local.storage_map : [
        for blob in sa.blobs : {
          key            = "${sa_key}::${blob.container_name}::${blob.name}"
          sa_key         = sa_key
          container_name = blob.container_name
          name           = blob.name
          content        = blob.content
        }
      ]
    ]) : b.key => b
  }

  # ---------------------------------------------------------------------------
  # entra_groups_map: var.entra_groups list → map keyed by the caller-supplied
  # `key`, the for_each index every azuread_* resource in entra.tf shares. That
  # same key is what tfvars ACEs reference via `id_ref` and what
  # local.resolved_storage resolves to an object ID below.
  # ---------------------------------------------------------------------------
  entra_groups_map = { for g in var.entra_groups : g.key => g }

  # ---------------------------------------------------------------------------
  # resolved_storage: var.storage's containers/paths with every ACE's `id_ref`
  # replaced by the object ID of the azuread_group entra.tf created under that
  # key. Group object IDs aren't knowable when variables.auto.tfvars.json is
  # authored, so tfvars references groups by key and the substitution happens
  # here — keeping every ACL authored as data in tfvars (the convention sa.tf
  # documents) rather than half of it in HCL.
  #
  # ACEs are rebuilt attribute-by-attribute so `id_ref` never reaches
  # module.adls_filesystem, whose acl object type has no such attribute.
  # ---------------------------------------------------------------------------
  resolved_storage = {
    for sa_key, sa in local.storage_map : sa_key => {
      containers = [
        for c in sa.containers : {
          container_name = c.container_name
          acl = [
            for a in c.acl : {
              scope       = a.scope
              type        = a.type
              permissions = a.permissions
              id          = a.id_ref != null ? azuread_group.this[a.id_ref].object_id : a.id
            }
          ]
        }
      ]
      paths = [
        for p in sa.paths : {
          container_name = p.container_name
          path_name      = p.path_name
          resource_type  = p.resource_type
          acl = [
            for a in p.acl : {
              scope       = a.scope
              type        = a.type
              permissions = a.permissions
              id          = a.id_ref != null ? azuread_group.this[a.id_ref].object_id : a.id
            }
          ]
        }
      ]
    }
  }

  # ---------------------------------------------------------------------------
  # container_arm_ids: classic ARM resource ID per (account, container), keyed
  # "<sa_key>::<container_name>" to match local.all_containers. Built directly
  # since azurerm_storage_blob needs this form rather than the DFS URL that
  # module.adls_filesystem.filesystem_ids returns.
  # ---------------------------------------------------------------------------
  container_arm_ids = {
    for k, v in local.all_containers :
    k => "${module.storage_account[v.sa_key].id}/blobServices/default/containers/${v.container_name}"
  }
}
