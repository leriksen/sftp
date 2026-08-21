"""ACL-parity control: the same two principals over the REST data plane.

Entra SFTP is documented as reusing Azure Blob Storage's ordinary access
control model, so the identical named group ACEs should produce the identical
allow/deny matrix whether reached over SFTP or over the Data Lake REST API.

Running both matters diagnostically. If the SFTP suites fail but these pass,
the ACLs are correct and SFTP is evaluating them differently -- a platform
finding. If both fail the same way, the ACL data itself is wrong. Without this
control the two are indistinguishable, which is exactly the ambiguity that made
the account "01" named-ACE investigation expensive (see project memory
sftp-acl-named-user-blocked).

These principals hold no RBAC, so every operation here is ACL-decided.
"""
import uuid

from conftest import (
    INBOUND_CONTAINER,
    OUTBOUND_CONTAINER,
    TREE_DIR,
    _log_created,
    _log_deleted,
    assert_denied,
)


# ── Reader ───────────────────────────────────────────────────────────────────

def test_reader_can_list_read_tree(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(OUTBOUND_CONTAINER)
    names = [p.name for p in fs.get_paths(path=f"{TREE_DIR}/sample", recursive=False)]
    assert f"{TREE_DIR}/sample/report.csv" in names


def test_reader_can_read_fixture(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(OUTBOUND_CONTAINER)
    data = fs.get_file_client(f"{TREE_DIR}/sample/report.csv").download_file().readall()
    assert data == b"id,value\n1,42\n2,7\n"


def test_reader_cannot_write(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(OUTBOUND_CONTAINER)
    fc = fs.get_file_client(f"{TREE_DIR}/sample/entra-reader-denied.txt")
    assert_denied(lambda: fc.upload_data(b"x", overwrite=True))


def test_reader_cannot_read_notsftp(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(OUTBOUND_CONTAINER)
    fc = fs.get_file_client("notsftp/secret.txt")
    assert_denied(lambda: fc.download_file().readall())


def test_reader_cannot_list_writer_tree(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(INBOUND_CONTAINER)
    assert_denied(lambda: list(fs.get_paths(path=TREE_DIR, recursive=False)))


# ── Writer ───────────────────────────────────────────────────────────────────

def test_writer_can_write_to_write_tree(entra_writer_client, admin_client):
    rel = f"{TREE_DIR}/entra-dataplane-probe-{uuid.uuid4().hex[:8]}.txt"
    fs = entra_writer_client.get_file_system_client(INBOUND_CONTAINER)
    fs.get_file_client(rel).upload_data(b"entra dataplane", overwrite=True)
    _log_created(INBOUND_CONTAINER, "file", rel)

    admin_fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    assert admin_fs.get_file_client(rel).download_file().readall() == b"entra dataplane"
    admin_fs.get_file_client(rel).delete_file()
    _log_deleted(INBOUND_CONTAINER, "file", rel)


def test_writer_cannot_read_notsftp(entra_writer_client):
    fs = entra_writer_client.get_file_system_client(INBOUND_CONTAINER)
    fc = fs.get_file_client("notsftp/secret.txt")
    assert_denied(lambda: fc.download_file().readall())


def test_writer_cannot_read_reader_tree(entra_writer_client):
    fs = entra_writer_client.get_file_system_client(OUTBOUND_CONTAINER)
    fc = fs.get_file_client(f"{TREE_DIR}/sample/report.csv")
    assert_denied(lambda: fc.download_file().readall())


def test_writer_cannot_list_reader_tree(entra_writer_client):
    fs = entra_writer_client.get_file_system_client(OUTBOUND_CONTAINER)
    assert_denied(lambda: list(fs.get_paths(path=TREE_DIR, recursive=False)))
