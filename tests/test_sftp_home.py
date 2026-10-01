"""
Home-directory tests, run once per SFTP local user (inbound / outbound).

Home: sftp-test/dev01/{inbound,outbound}/sterling
ACL:  user::rwx other::rwx, default:user::rwx default:other::rwx

The default entries are what make nested work possible: a directory the user
creates inherits them as both its access and its default ACL, so the user
can keep creating files and directories at any depth. user:: matters
because Azure makes the uploading local user ("lu-<userId>") the owner of
what it creates.

Requirement covered: each user can create, read and delete files in its
home, create directories there, and create files and directories inside
those.
"""
import io
import uuid

from conftest import CONTAINER, sftp_path


def _rid():
    return uuid.uuid4().hex[:8]


# ── ALLOW: land in home ──────────────────────────────────────────────────────

def test_lands_in_home(user, fresh_sftp):
    sftp = fresh_sftp(user.name)
    assert sftp.normalize(".") == sftp_path(user.home)


def test_can_list_home(user):
    assert isinstance(user.client.listdir(sftp_path(user.home)), list)


# ── ALLOW: create, read, delete a file ───────────────────────────────────────

def test_create_read_delete_file(user, container_cleanup):
    rel  = f"{user.home}/file-{_rid()}.txt"
    data = f"from {user.name}".encode()
    container_cleanup.append(("file", rel, CONTAINER))

    user.client.putfo(io.BytesIO(data), sftp_path(rel))

    buf = io.BytesIO()
    user.client.getfo(sftp_path(rel), buf)
    assert buf.getvalue() == data
    assert rel.rsplit("/", 1)[1] in user.client.listdir(sftp_path(user.home))

    user.client.remove(sftp_path(rel))
    assert rel.rsplit("/", 1)[1] not in user.client.listdir(sftp_path(user.home))


# ── ALLOW: create a directory, then a file inside it ─────────────────────────
# The reporter's steps 4-5, verbatim: relative mkdir from the landing dir,
# then put into ./<new dir>/. Uses a fresh connection because it relies on
# the landing cwd.

def test_put_into_new_subdir_relative(user, fresh_sftp, admin_client, container_cleanup):
    sftp   = fresh_sftp(user.name)
    folder = f"folder-{_rid()}"
    container_cleanup.append(("dir", f"{user.home}/{folder}", CONTAINER))
    container_cleanup.append(("file", f"{user.home}/{folder}/testfile.txt", CONTAINER))

    sftp.mkdir(folder)
    sftp.putfo(io.BytesIO(b"testfile"), f"./{folder}/testfile.txt")

    fs = admin_client.get_file_system_client(CONTAINER)
    assert fs.get_file_client(f"{user.home}/{folder}/testfile.txt").download_file().readall() == b"testfile"


# ── ALLOW: nested directories and files, created, read and deleted ──────────

def test_nested_dirs_and_files(user, admin_client, container_cleanup):
    top    = f"{user.home}/nest-{_rid()}"
    levels = [top, f"{top}/a", f"{top}/a/b"]
    files  = [f"{d}/f.txt" for d in levels]

    for d, f in zip(levels, files):
        container_cleanup.append(("dir", d, CONTAINER))
        user.client.mkdir(sftp_path(d))
        container_cleanup.append(("file", f, CONTAINER))
        user.client.putfo(io.BytesIO(f.encode()), sftp_path(f))

    for d, f in zip(levels, files):
        buf = io.BytesIO()
        user.client.getfo(sftp_path(f), buf)
        assert buf.getvalue() == f.encode()
        assert "f.txt" in user.client.listdir(sftp_path(d))

    # Delete bottom-up over SFTP, proving the user can remove what it built.
    for d, f in reversed(list(zip(levels, files))):
        user.client.remove(sftp_path(f))
        user.client.rmdir(sftp_path(d))

    fs = admin_client.get_file_system_client(CONTAINER)
    assert not fs.get_directory_client(top).exists()
