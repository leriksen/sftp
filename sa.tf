# ---------------------------------------------------------------------------
# Storage account
#
# Vendored from github.com/leriksen/terraform-azurerm-storage-account (also
# published to the private registry at app.terraform.io/leif-lab3) rather than
# sourced from the registry directly — see modules/storage-account/README.md.
# This local fork adds a `name` variable (default null, not present upstream)
# because the upstream module's default naming convention
# ("<resource_group_name>dl<sequence_no>") doesn't match this storage
# account's existing real name, and `name` is ForceNew: pointing at the
# published module (as module.adls_filesystem and module.sftp_local_users do
# below) would force a replace of the real storage account.
# ---------------------------------------------------------------------------
module "storage_account" {
  source = "./modules/storage-account"

  name                = var.storage_account_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sequence_no         = var.storage_account_sequence_no
  sftp_enabled        = true
}

# Preserves the existing storage account's state entry across the move from a
# root resource into this module — without this, Terraform would plan to
# destroy and recreate it.
moved {
  from = azurerm_storage_account.this
  to   = module.storage_account.azurerm_storage_account.this
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

resource "azurerm_role_assignment" "tf_executor_blob_owner" {
  scope                = module.storage_account.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "aad_reader" {
  scope                = module.storage_account.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = var.aad_reader_object_id
  principal_type       = "Group"
}

resource "azurerm_role_assignment" "aad_writer" {
  scope                = module.storage_account.id
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
# module (github.com/leriksen/terraform-azurerm-adls-filesystem) — sourced from
# the private registry at app.terraform.io/leif-lab3, same module and version
# pin the sibling adls project uses. Its `acl` blocks map straight onto
# azurerm_storage_data_lake_gen2_filesystem/_path `ace` blocks, including
# `type = "other"` with no `id` — the only ACE type an SFTP local user can
# ever be authorized through (named user/group ACEs are rejected by the
# platform, InvalidNamedUserOrNamedGroup — see project memory
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

module "adls_filesystem" {
  source  = "app.terraform.io/leif-lab3/terraform-azurerm-adls-filesystem/azurerm"
  version = "0.2.1"

  storage_account_id = module.storage_account.id

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
