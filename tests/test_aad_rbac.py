"""
AAD/RBAC access tests -- proves Storage Blob Data Reader granted to the
ADLS_Reader AAD group (azurerm_role_assignment.aad_reader in main.tf, object
ID reused from the sibling adls project) works as an access path entirely
independent of the SFTP local-user ACL scheme exercised in test_sftp_*.py
and test_notsftp_denied.py. Per Microsoft's own docs, local users do not
interoperate with RBAC -- this suite verifies that's actually true here, not
assumed.
"""
import pytest
from conftest import assert_denied, INBOUND_CONTAINER, OUTBOUND_CONTAINER


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
