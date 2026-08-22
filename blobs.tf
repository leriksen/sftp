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
# The fixture set is authored per account in variables.auto.tfvars.json rather
# than hardcoded here, because the two accounts no longer share a container
# layout: "01" splits inbound/outbound across two containers (the most one
# SFTP local user per container allows), while "02" puts both trees inside a
# single container. Same bytes, same relative paths — only the container
# boundary and the authorization model differ, which is the comparison.
# ---------------------------------------------------------------------------

resource "azurerm_storage_blob" "fixture" {
  for_each = local.all_blobs

  name                 = each.value.name
  storage_container_id = local.container_arm_ids["${each.value.sa_key}::${each.value.container_name}"]
  type                 = "Block"
  source_content       = each.value.content

  depends_on = [module.adls_filesystem]
}
