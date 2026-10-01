"""
KNOWN, ACCEPTED OVERLAP between the two local users -- the reported bug.

SFTP local users can only be authorized through "other::" ACEs (named
local-user ACEs are rejected by the platform, InvalidNamedUserOrNamedGroup),
and other:: is shared by every local user on the account. The rwx each home
grants its own user therefore applies to the other user too.

These tests assert that the overlap EXISTS, reproducing the bug report
(FTPUSER1 writes into outbound/sterling, FTPUSER2 into inbound/sterling via
"cd ../../<other>/sterling"). They are not a statement that the behaviour is
desirable. If one starts failing, platform behaviour has changed (e.g. named
local-user ACEs became supported) and the layout should be revisited -- see
sa.tf.
"""
import io
import uuid

from conftest import CONTAINER, sftp_path


def _rid():
    return uuid.uuid4().hex[:8]


def _relative_other_home(user):
    # dev01/inbound/sterling -> ../../outbound/sterling (and vice versa),
    # exactly as typed in the bug report.
    return "../../" + "/".join(user.other_home.split("/")[1:])


def test_known_overlap_can_cd_and_write_into_other_home(user, fresh_sftp, admin_client, container_cleanup):
    sftp = fresh_sftp(user.name)
    name = f"overlap-{user.name}-{_rid()}.txt"
    container_cleanup.append(("file", f"{user.other_home}/{name}", CONTAINER))

    sftp.chdir(_relative_other_home(user))
    sftp.putfo(io.BytesIO(b"cross write"), name)

    fs = admin_client.get_file_system_client(CONTAINER)
    assert fs.get_file_client(f"{user.other_home}/{name}").download_file().readall() == b"cross write"


def test_known_overlap_can_read_other_home(user, admin_client, container_cleanup):
    rel = f"{user.other_home}/overlap-read-{_rid()}.txt"
    container_cleanup.append(("file", rel, CONTAINER))
    admin_client.get_file_system_client(CONTAINER).get_file_client(rel).upload_data(b"theirs", overwrite=True)

    buf = io.BytesIO()
    user.client.getfo(sftp_path(rel), buf)
    assert buf.getvalue() == b"theirs"
    assert rel.rsplit("/", 1)[1] in user.client.listdir(sftp_path(user.other_home))


def test_known_overlap_can_delete_in_other_home(user, admin_client, container_cleanup):
    rel = f"{user.other_home}/overlap-delete-{_rid()}.txt"
    container_cleanup.append(("file", rel, CONTAINER))
    fs = admin_client.get_file_system_client(CONTAINER)
    fs.get_file_client(rel).upload_data(b"theirs", overwrite=True)

    user.client.remove(sftp_path(rel))
    assert not fs.get_file_client(rel).exists()
