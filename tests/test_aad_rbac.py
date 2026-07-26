"""
AAD/RBAC access tests -- proves Storage Blob Data Reader / Contributor
granted to the ADLS_Reader / ADLS_Write AAD groups (azurerm_role_assignment.
aad_reader / aad_writer in main.tf, object IDs reused from the sibling adls
project) work as access paths entirely independent of the SFTP local-user
ACL scheme exercised in test_sftp_*.py and test_notsftp_denied.py. Per
Microsoft's own docs, local users do not interoperate with RBAC -- this
suite verifies that's actually true here, not assumed.

Both role assignments were verified empirically before being added: the
reader group's test SP already had working read access (so aad_reader
predates this suite); the writer group's test SP had zero access (403
AuthorizationPermissionMismatch) until azurerm_role_assignment.aad_writer
was added.
"""
import uuid

import pytest
from conftest import assert_denied, INBOUND_CONTAINER, OUTBOUND_CONTAINER, _log_created, _log_deleted


# ── ALLOW: read across both containers, unaffected by the SFTP ACL scheme ───

@pytest.mark.parametrize("container", [INBOUND_CONTAINER, OUTBOUND_CONTAINER])
def test_can_list_container_root(aad_reader_client, container):
    paths = list(aad_reader_client.get_file_system_client(container).get_paths(path=""))
    assert isinstance(paths, list)


def test_can_read_outbound_sample_fixture(aad_reader_client):
    fc = aad_reader_client.get_file_system_client(OUTBOUND_CONTAINER).get_file_client(
        "dev01/sample/report.csv"
    )
    assert fc.download_file().readall() == b"id,value\n1,42\n2,7\n"


def test_can_read_notsftp_via_rbac(aad_reader_client):
    """RBAC access is unaffected by the SFTP-local-user-focused notsftp deny
    ACLs -- the Reader role sees this content fine, proving the two access
    mechanisms are properly independent."""
    fc = aad_reader_client.get_file_system_client(INBOUND_CONTAINER).get_file_client(
        "notsftp/secret.txt"
    )
    assert fc.download_file().readall() == b"not for sftp users\n"


# ── DENY: writes (Reader role, not Contributor/Owner) ────────────────────────

def test_cannot_write(aad_reader_client):
    fc = aad_reader_client.get_file_system_client(OUTBOUND_CONTAINER).get_file_client(
        "dev01/sample/reader-denied.txt"
    )
    assert_denied(lambda: fc.upload_data(b"x", overwrite=True))


def test_cannot_delete(aad_reader_client):
    fc = aad_reader_client.get_file_system_client(OUTBOUND_CONTAINER).get_file_client(
        "dev01/sample/report.csv"
    )
    assert_denied(fc.delete_file)


# ── writer (Storage Blob Data Contributor via ADLS_Write): allow r/w/d ───────

@pytest.mark.parametrize("container", [INBOUND_CONTAINER, OUTBOUND_CONTAINER])
def test_writer_can_list_container_root(aad_writer_client, container):
    paths = list(aad_writer_client.get_file_system_client(container).get_paths(path=""))
    assert isinstance(paths, list)


def test_writer_can_write_read_and_delete(aad_writer_client):
    rel = f"dev01/sample/rbac-writer-probe-{uuid.uuid4().hex[:8]}.txt"
    fc = aad_writer_client.get_file_system_client(OUTBOUND_CONTAINER).get_file_client(rel)

    fc.upload_data(b"written via aad_writer_client", overwrite=True)
    _log_created(OUTBOUND_CONTAINER, "file", rel)
    assert fc.download_file().readall() == b"written via aad_writer_client"

    fc.delete_file()
    _log_deleted(OUTBOUND_CONTAINER, "file", rel)
    assert not fc.exists()


def test_writer_can_read_notsftp_via_rbac(aad_writer_client):
    """Same independence proof as test_can_read_notsftp_via_rbac, from the
    writer side: the notsftp deny ACLs target SFTP local users, not RBAC
    principals."""
    fc = aad_writer_client.get_file_system_client(INBOUND_CONTAINER).get_file_client(
        "notsftp/secret.txt"
    )
    assert fc.download_file().readall() == b"not for sftp users\n"
