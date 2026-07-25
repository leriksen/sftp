"""
notsftp deny tests -- both SFTP local users must be denied all access here,
regardless of what the container-root ACL experiment does. This tree exists
in every container specifically to prove ACL denial holds even for content
nested under a user's own reachable container, addressed explicitly rather
than relying on inherited defaults (main.tf sets other::--- directly on
notsftp and notsftp/private, both access and default scope).
"""
import io
from conftest import assert_sftp_denied, INBOUND_CONTAINER, OUTBOUND_CONTAINER


def test_notsftp_files_actually_exist(admin_client):
    """Sanity check: the denials below are real permission denials, not the
    files simply not existing."""
    for container in (INBOUND_CONTAINER, OUTBOUND_CONTAINER):
        fs = admin_client.get_file_system_client(container)
        assert fs.get_file_client("notsftp/secret.txt").exists()
        assert fs.get_file_client("notsftp/private/data.txt").exists()


def test_inbound_cannot_list_notsftp(sftp_inbound_client):
    assert_sftp_denied(lambda: sftp_inbound_client.listdir("../notsftp"))


def test_inbound_cannot_enter_notsftp_private(sftp_inbound_client):
    assert_sftp_denied(lambda: sftp_inbound_client.chdir("../notsftp/private"))


def test_inbound_cannot_read_notsftp_secret(sftp_inbound_client):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: sftp_inbound_client.getfo("../notsftp/secret.txt", buf))


def test_inbound_cannot_write_notsftp(sftp_inbound_client):
    assert_sftp_denied(lambda: sftp_inbound_client.putfo(io.BytesIO(b"x"), "../notsftp/denied.txt"))


def test_outbound_cannot_list_notsftp(sftp_outbound_client):
    assert_sftp_denied(lambda: sftp_outbound_client.listdir("../notsftp"))


def test_outbound_cannot_enter_notsftp_private(sftp_outbound_client):
    assert_sftp_denied(lambda: sftp_outbound_client.chdir("../notsftp/private"))


def test_outbound_cannot_read_notsftp_secret(sftp_outbound_client):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: sftp_outbound_client.getfo("../notsftp/secret.txt", buf))


def test_outbound_cannot_read_notsftp_private_data(sftp_outbound_client):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: sftp_outbound_client.getfo("../notsftp/private/data.txt", buf))
