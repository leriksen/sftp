resource "azurerm_storage_account" "this" {
  name                     = var.storage_account_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true # ADLS Gen2 — required for SFTP AND ACLs
  sftp_enabled             = true
  min_tls_version          = "TLS1_2"
}

# ---------------------------------------------------------------------------
# RBAC: the Terraform executor needs data-plane rights for module.adls_filesystem
# below (storage_use_azuread = true routes those calls through AAD, not a
# shared key). Also grants two real AAD groups (reused from the adls project:
# "ADLS_Reader" / "ADLS_Write") Storage Blob Data Reader / Contributor, so
# tests can prove RBAC-based access works independently of — and isn't
# affected by — the SFTP local-user ACL scheme (local users do not
# interoperate with RBAC). Verified empirically before adding: the reader
# group's test SP already had working read access via ADLS_Reader; the
# writer group's test SP had none (403 AuthorizationPermissionMismatch)
# until this aad_writer assignment was added.
# ---------------------------------------------------------------------------

data "azurerm_client_config" "current" {}

resource "azurerm_role_assignment" "tf_executor_blob_owner" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "aad_reader" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = var.aad_reader_object_id
  principal_type       = "Group"
}

resource "azurerm_role_assignment" "aad_writer" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.aad_writer_object_id
  principal_type       = "Group"
}

resource "time_sleep" "rbac_wait" {
  depends_on = [
    azurerm_role_assignment.tf_executor_blob_owner,
    azurerm_role_assignment.aad_reader,
    azurerm_role_assignment.aad_writer,
  ]
  create_duration = "30s"
}

# ---------------------------------------------------------------------------
# Containers + POSIX ACL tree, via the published terraform-azurerm-adls-filesystem
# module (github.com/leriksen/terraform-azurerm-adls-filesystem). Its `acl`
# blocks map straight onto azurerm_storage_data_lake_gen2_filesystem/_path
# `ace` blocks, including `type = "other"` with no `id` — the only ACE type an
# SFTP local user can ever be authorized through (named user/group ACEs are
# rejected by the platform, InvalidNamedUserOrNamedGroup — see project memory
# sftp_acl_named_user_blocked).
#
# Setting the ACL directly on the azurerm_storage_data_lake_gen2_filesystem
# resource (via containers[].acl) is what makes the container-root ACL work
# at all: a separate azurerm_storage_data_lake_gen2_path with path = ""
# fails with "resource already exists" (the filesystem root always
# implicitly exists the moment the container does, and that resource's
# create-only semantics can't adopt it without a manual `terraform import`).
#
# SAFETY INVARIANT: every "other" grant below is scoped to a container that
# has exactly one SFTP local user. "other" is shared by every local user in a
# container — adding a second SFTP user to an existing container would
# silently inherit these grants too. This is exactly how the sibling adls
# project's push/pull isolation broke (see plan/memory). Don't add a second
# SFTP local user to inbound/outbound without redesigning this.
# ---------------------------------------------------------------------------

locals {
  notsftp_deny_acl = [
    { scope = "access", id = null, type = "other", permissions = "---" },
    { scope = "default", id = null, type = "other", permissions = "---" },
  ]
}

module "adls_filesystem" {
  source = "./modules/adls"

  storage_account_id = azurerm_storage_account.this.id

  containers = [
    for c in var.containers : {
      container_name = c
      # other::--x is traverse-only: no listing/reading of root's own
      # entries, but execute is present so the ACL evaluation chain isn't
      # broken. EXPERIMENTALLY CONFIRMED other::--- (full deny) breaks this:
      # Microsoft's docs require execute on "the root folder of the
      # container, and to each folder in the hierarchy" for ANY ACL-gated
      # read/write to succeed, not just for reaching dev01 — with --- there,
      # every ACL-gated operation in the whole container failed with
      # AuthorizationPermissionMismatch, confirmed via a live test run.
      acl = [
        { scope = "access", id = null, type = "other", permissions = "--x" },
      ]
    }
  ]

  paths = concat(
    # dev01 — each user's home directory. access ACE governs the directory
    # node itself (its "list contents" and "traverse" bits); default ACE is
    # what new children (files the user uploads, or the outbound sample
    # fixtures below) inherit as their own access ACL at creation. These
    # differ for inbound: it needs the access ACE's `r` to list its own home
    # dir (list is intentionally NOT granted via permission_scopes below --
    # container-level permissions apply account-wide across the whole
    # container per Microsoft's docs, which would also unlock listing
    # notsftp; confirmed via a live test run: granting `list` at
    # permission_scopes let both users list/enter notsftp despite its deny
    # ACL, since sufficient container-level permission skips ACL evaluation
    # entirely), but its uploaded files should stay unreadable by inbound
    # itself, hence default ACE omits `r`.
    #
    # Both `other` AND the unnamed `user` (owner placeholder, NOT a named-user
    # ACE -- id stays null) entries are set to the same rights. Confirmed via
    # a live probe: when a local user creates a file, Azure makes it the
    # file's owner (owner: "lu-<userId>"), and the new file's owner
    # permission bits come from the parent's default:user:: entry -- which
    # defaults to a permissive rwx if left untouched, letting inbound read
    # back files it just wrote regardless of the default:other restriction.
    # Setting default:user:: to match closes that gap.
    [
      for uname, u in var.sftp_users : {
        container_name = u.container
        path_name      = "dev01"
        acl = [
          { scope = "access", id = null, type = "other", permissions = u.home_dir_rights },
          { scope = "access", id = null, type = "user", permissions = u.home_dir_rights },
          { scope = "default", id = null, type = "other", permissions = u.home_default_rights },
          { scope = "default", id = null, type = "user", permissions = u.home_default_rights },
        ]
      }
    ],
    # notsftp — explicit deny tree in each container, independent of
    # whatever the root ends up doing.
    [
      for c in var.containers : {
        container_name = c
        path_name      = "notsftp"
        acl            = local.notsftp_deny_acl
      }
    ],
    [
      for c in var.containers : {
        container_name = c
        path_name      = "notsftp/private"
        acl            = local.notsftp_deny_acl
      }
    ],
    # Outbound test fixtures: a small directory/file tree the read-only
    # outbound user can list/read during tests. Admin-owned (created by the
    # Terraform executor's RBAC identity), not by the outbound SFTP user
    # itself, since that user has no write access anywhere.
    [
      {
        container_name = "outbound"
        path_name      = "dev01/sample"
        acl = [
          { scope = "access", id = null, type = "other", permissions = "r-x" },
          { scope = "default", id = null, type = "other", permissions = "r-x" },
        ]
      },
      {
        container_name = "outbound"
        path_name      = "dev01/sample/nested"
        acl = [
          { scope = "access", id = null, type = "other", permissions = "r-x" },
          { scope = "default", id = null, type = "other", permissions = "r-x" },
        ]
      },
    ],
  )

  depends_on = [
    azurerm_role_assignment.tf_executor_blob_owner,
    azurerm_role_assignment.aad_reader,
    time_sleep.rbac_wait,
  ]
}

# ---------------------------------------------------------------------------
# SFTP local users, via the published terraform-azurerm-sftp-local-users
# module (github.com/leriksen/terraform-azurerm-sftp-local-users). Names
# aren't settable — the module names local users "sftpuser<sequence_number>"
# — so the inbound/outbound intent lives in home_directory instead of the
# login name (same convention the sibling adls project already uses).
#
# No container-level permission_scopes at all: Microsoft's docs guarantee a
# connection succeeds as long as the user has ACL permission to their home
# directory ("the local user must have at least one container permission OR
# ACL permission to the home directory ... otherwise the connection
# fails") — which module.adls_filesystem's dev01 ACL above provides. Any
# container-level grant (even just List) applies account-wide across the
# whole container and would bypass the notsftp deny ACL entirely, per the
# live-test finding above.
# ---------------------------------------------------------------------------

module "sftp_local_users" {
  source = "./modules/sftp"

  storage_account_id = azurerm_storage_account.this.id

  sftp_users = [
    for uname, u in var.sftp_users : {
      sequence_number         = u.sequence_number
      home_directory          = "${u.container}/dev01"
      allow_acl_authorization = true
      permission_scopes       = []
      ssh_authorized_keys = u.ssh_key != null ? [
        { key = u.ssh_key, description = "${uname}-key" }
      ] : []
    }
  ]

  depends_on = [module.adls_filesystem]
}

# ---------------------------------------------------------------------------
# Leaf files. Neither module creates blobs, and azurerm_storage_blob has no
# `ace` block, so these rely on the parent directory's default ACE being
# applied at creation time (standard ADLS Gen2 platform behaviour). tests/
# verifies this lands as expected.
#
# azurerm_storage_blob.storage_container_id needs the classic ARM resource ID
# (".../blobServices/default/containers/<name>"), not the DFS URL that
# module.adls_filesystem.filesystem_ids returns (the ADLS Gen2 filesystem
# resource's own .id) — built directly rather than depending on a container
# resource we no longer create ourselves.
# ---------------------------------------------------------------------------

locals {
  container_arm_ids = {
    for c in var.containers : c => "${azurerm_storage_account.this.id}/blobServices/default/containers/${c}"
  }
}

resource "azurerm_storage_blob" "notsftp_secret" {
  for_each = toset(var.containers)

  name                 = "notsftp/secret.txt"
  storage_container_id = local.container_arm_ids[each.value]
  type                 = "Block"
  source_content       = "not for sftp users\n"

  depends_on = [module.adls_filesystem]
}

resource "azurerm_storage_blob" "notsftp_private_data" {
  for_each = toset(var.containers)

  name                 = "notsftp/private/data.txt"
  storage_container_id = local.container_arm_ids[each.value]
  type                 = "Block"
  source_content       = "not for sftp users either\n"

  depends_on = [module.adls_filesystem]
}

resource "azurerm_storage_blob" "outbound_sample_report" {
  name                 = "dev01/sample/report.csv"
  storage_container_id = local.container_arm_ids["outbound"]
  type                 = "Block"
  source_content       = "id,value\n1,42\n2,7\n"

  depends_on = [module.adls_filesystem]
}

resource "azurerm_storage_blob" "outbound_sample_notes" {
  name                 = "dev01/sample/notes.txt"
  storage_container_id = local.container_arm_ids["outbound"]
  type                 = "Block"
  source_content       = "sample outbound fixture data\n"

  depends_on = [module.adls_filesystem]
}

resource "azurerm_storage_blob" "outbound_sample_nested_extra" {
  name                 = "dev01/sample/nested/extra.txt"
  storage_container_id = local.container_arm_ids["outbound"]
  type                 = "Block"
  source_content       = "nested fixture data\n"

  depends_on = [module.adls_filesystem]
}
