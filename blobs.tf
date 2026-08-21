# ---------------------------------------------------------------------------
# Leaf files. Neither module creates blobs, and azurerm_storage_blob has no
# `ace` block, so these rely on the parent directory's default ACE being
# applied at creation time (standard ADLS Gen2 platform behaviour). tests/
# verifies this lands as expected.
#
# azurerm_storage_blob.storage_container_id needs the classic ARM resource ID
# (".../blobServices/default/containers/<name>"), not the DFS URL that
# module.adls_filesystem.filesystem_ids returns (the ADLS Gen2 filesystem
# resource's own .id) — see local.container_arm_ids in locals.tf.
#
# Every for_each here is keyed "<sa_key>::<container_name>", so both storage
# accounts get an identical fixture set: account "01" (SFTP local users) and
# account "02" (Entra principals) differ only in how access to these same
# bytes is authorized, which is what makes the two directly comparable.
# ---------------------------------------------------------------------------

resource "azurerm_storage_blob" "notsftp_secret" {
  for_each = local.all_containers

  name                 = "notsftp/secret.txt"
  storage_container_id = local.container_arm_ids[each.key]
  type                 = "Block"
  source_content       = "not for sftp users\n"

  depends_on = [module.adls_filesystem]
}

resource "azurerm_storage_blob" "notsftp_private_data" {
  for_each = local.all_containers

  name                 = "notsftp/private/data.txt"
  storage_container_id = local.container_arm_ids[each.key]
  type                 = "Block"
  source_content       = "not for sftp users either\n"

  depends_on = [module.adls_filesystem]
}

resource "azurerm_storage_blob" "outbound_sample_report" {
  for_each = local.outbound_containers

  name                 = "dev01/sample/report.csv"
  storage_container_id = local.container_arm_ids[each.key]
  type                 = "Block"
  source_content       = "id,value\n1,42\n2,7\n"

  depends_on = [module.adls_filesystem]
}

resource "azurerm_storage_blob" "outbound_sample_notes" {
  for_each = local.outbound_containers

  name                 = "dev01/sample/notes.txt"
  storage_container_id = local.container_arm_ids[each.key]
  type                 = "Block"
  source_content       = "sample outbound fixture data\n"

  depends_on = [module.adls_filesystem]
}

resource "azurerm_storage_blob" "outbound_sample_nested_extra" {
  for_each = local.outbound_containers

  name                 = "dev01/sample/nested/extra.txt"
  storage_container_id = local.container_arm_ids[each.key]
  type                 = "Block"
  source_content       = "nested fixture data\n"

  depends_on = [module.adls_filesystem]
}
