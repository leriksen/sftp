locals {
  users_by_sequence = { for u in var.sftp_users : u.sequence_number => u }
}
