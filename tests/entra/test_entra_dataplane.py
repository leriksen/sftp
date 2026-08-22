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

Both principals share a single container here, so every client below is built
against the *same* file system and differs only in which group its SP is a
member of. These principals hold no RBAC, so every operation is ACL-decided.
"""
import uuid

from conftest import (
    READ_DIR,
    READ_TREE_REL,
    SFTP_CONTAINER,
    WRITE_DIR,
    WRITE_TREE_REL,
    _log_created,
    _log_deleted,
    assert_denied,
)


# ── Reader ───────────────────────────────────────────────────────────────────

def test_reader_can_list_read_tree(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(SFTP_CONTAINER)
    names = [p.name for p in fs.get_paths(path=f"{READ_TREE_REL}/sample", recursive=False)]
    assert f"{READ_TREE_REL}/sample/report.csv" in names


def test_reader_can_read_fixture(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(SFTP_CONTAINER)
    data = fs.get_file_client(f"{READ_TREE_REL}/sample/report.csv").download_file().readall()
    assert data == b"id,value\n1,42\n2,7\n"


def test_reader_cannot_write(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(SFTP_CONTAINER)
    fc = fs.get_file_client(f"{READ_TREE_REL}/sample/entra-reader-denied.txt")
    assert_denied(lambda: fc.upload_data(b"x", overwrite=True))


def test_reader_cannot_read_notsftp(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(SFTP_CONTAINER)
    fc = fs.get_file_client("notsftp/secret.txt")
    assert_denied(lambda: fc.download_file().readall())


def test_reader_cannot_list_container_root(entra_reader_client):
    """`--x` on the container root is traverse-only, so the reader cannot
    enumerate it and discover the writer's subtree."""
    fs = entra_reader_client.get_file_system_client(SFTP_CONTAINER)
    assert_denied(lambda: list(fs.get_paths(recursive=False)))


def test_reader_cannot_list_writer_subtree(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(SFTP_CONTAINER)
    assert_denied(lambda: list(fs.get_paths(path=WRITE_DIR, recursive=False)))


def test_reader_cannot_list_writer_tree(entra_reader_client):
    fs = entra_reader_client.get_file_system_client(SFTP_CONTAINER)
    assert_denied(lambda: list(fs.get_paths(path=WRITE_TREE_REL, recursive=False)))


# ── Writer ───────────────────────────────────────────────────────────────────

def test_writer_can_write_to_write_tree(entra_writer_client, admin_client):
    rel = f"{WRITE_TREE_REL}/entra-dataplane-probe-{uuid.uuid4().hex[:8]}.txt"
    fs = entra_writer_client.get_file_system_client(SFTP_CONTAINER)
    fs.get_file_client(rel).upload_data(b"entra dataplane", overwrite=True)
    _log_created(SFTP_CONTAINER, "file", rel)

    admin_fs = admin_client.get_file_system_client(SFTP_CONTAINER)
    assert admin_fs.get_file_client(rel).download_file().readall() == b"entra dataplane"
    admin_fs.get_file_client(rel).delete_file()
    _log_deleted(SFTP_CONTAINER, "file", rel)


def test_writer_cannot_read_notsftp(entra_writer_client):
    fs = entra_writer_client.get_file_system_client(SFTP_CONTAINER)
    fc = fs.get_file_client("notsftp/secret.txt")
    assert_denied(lambda: fc.download_file().readall())


def test_writer_cannot_list_container_root(entra_writer_client):
    fs = entra_writer_client.get_file_system_client(SFTP_CONTAINER)
    assert_denied(lambda: list(fs.get_paths(recursive=False)))


def test_writer_cannot_read_reader_fixture(entra_writer_client):
    fs = entra_writer_client.get_file_system_client(SFTP_CONTAINER)
    fc = fs.get_file_client(f"{READ_TREE_REL}/sample/report.csv")
    assert_denied(lambda: fc.download_file().readall())


def test_writer_cannot_list_reader_subtree(entra_writer_client):
    fs = entra_writer_client.get_file_system_client(SFTP_CONTAINER)
    assert_denied(lambda: list(fs.get_paths(path=READ_DIR, recursive=False)))


def test_writer_cannot_list_reader_tree(entra_writer_client):
    fs = entra_writer_client.get_file_system_client(SFTP_CONTAINER)
    assert_denied(lambda: list(fs.get_paths(path=READ_TREE_REL, recursive=False)))


def test_writer_cannot_write_to_reader_tree(entra_writer_client):
    """Same file system client, same container -- only the ACL differs."""
    fs = entra_writer_client.get_file_system_client(SFTP_CONTAINER)
    fc = fs.get_file_client(f"{READ_TREE_REL}/sample/entra-writer-denied.txt")
    assert_denied(lambda: fc.upload_data(b"x", overwrite=True))
