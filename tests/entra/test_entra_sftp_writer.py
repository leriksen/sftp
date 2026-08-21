"""Writer-side Entra SFTP permission tests (storage account "02").

Principal:  service principal in the sftp-entra-writers group.
RBAC:       none. Every allow and deny below is decided by a named group ACE.
ACL:        inbound/          access group:writers::--x  (traverse only)
            inbound/dev01     access group:writers::rwx, default ::-wx
            everything else   no ACE for this group at all

That ACL is the deliberate mirror of what `other::` gives sftpuser0 on account
"01" -- rwx on the tree root so it can list it, -wx inherited by everything
created inside so content can be pushed but never read back. The point of the
comparison is that here the grant is attached to a *named group* rather than
to `other`, which is what makes more than one isolated principal per container
possible at all.

No home directory: Entra SFTP does not support one, so every path is
container-qualified rather than home-relative.
"""
import io
import uuid

from conftest import (
    INBOUND_CONTAINER,
    OUTBOUND_CONTAINER,
    TREE_DIR,
    WRITE_TREE,
    _log_created,
    _log_deleted,
    assert_sftp_denied,
)


# ── ALLOW: connect and reach the write tree ─────────────────────────────────

def test_can_connect(entra_writer_sftp):
    """Connecting at all is the first finding: this SP holds no RBAC, so a
    successful session proves an ACL alone is sufficient to authenticate and
    land on the account root."""
    assert entra_writer_sftp.listdir(WRITE_TREE) is not None


def test_can_list_write_tree(entra_writer_sftp):
    entries = entra_writer_sftp.listdir(WRITE_TREE)
    assert isinstance(entries, list)


# ── ALLOW: create ────────────────────────────────────────────────────────────

def test_upload_file(entra_writer_sftp, admin_client, container_cleanup):
    rel = f"entra-writer-upload-{uuid.uuid4().hex[:8]}.txt"
    # confirm=False: the inherited default ACE grants write+execute but not
    # read, and putfo's default post-upload stat needs read.
    entra_writer_sftp.putfo(io.BytesIO(b"entra writer data"), f"{WRITE_TREE}/{rel}", confirm=False)
    container_cleanup.append(("file", f"{TREE_DIR}/{rel}", INBOUND_CONTAINER))

    # The writer can't read back what it wrote -- verify out-of-band.
    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    fc = fs.get_file_client(f"{TREE_DIR}/{rel}")
    assert fc.exists()
    assert fc.download_file().readall() == b"entra writer data"


def test_create_subdir(entra_writer_sftp, admin_client, container_cleanup):
    rel = f"entra-writer-dir-{uuid.uuid4().hex[:8]}"
    entra_writer_sftp.mkdir(f"{WRITE_TREE}/{rel}")
    container_cleanup.append(("dir", f"{TREE_DIR}/{rel}", INBOUND_CONTAINER))
    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    assert fs.get_directory_client(f"{TREE_DIR}/{rel}").exists()


# ── ALLOW: delete within its own tree ────────────────────────────────────────
# POSIX bundles create and delete into the directory's `w` bit, so a
# create-only grant isn't expressible here any more than it was on account 01.

def test_can_delete_own_file(entra_writer_sftp, admin_client):
    rel = f"entra-writer-delete-probe-{uuid.uuid4().hex[:8]}.txt"
    entra_writer_sftp.putfo(io.BytesIO(b"x"), f"{WRITE_TREE}/{rel}", confirm=False)
    _log_created(INBOUND_CONTAINER, "file", f"{TREE_DIR}/{rel}")
    entra_writer_sftp.remove(f"{WRITE_TREE}/{rel}")
    _log_deleted(INBOUND_CONTAINER, "file", f"{TREE_DIR}/{rel}")
    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    assert not fs.get_file_client(f"{TREE_DIR}/{rel}").exists()


# ── DENY: read back its own content (default ACE is -wx, no `r`) ────────────

def test_cannot_read_own_file(entra_writer_sftp, admin_client, container_cleanup):
    rel = f"entra-writer-readback-{uuid.uuid4().hex[:8]}.txt"
    entra_writer_sftp.putfo(io.BytesIO(b"no readback"), f"{WRITE_TREE}/{rel}", confirm=False)
    container_cleanup.append(("file", f"{TREE_DIR}/{rel}", INBOUND_CONTAINER))
    buf = io.BytesIO()
    assert_sftp_denied(lambda: entra_writer_sftp.getfo(f"{WRITE_TREE}/{rel}", buf))


def test_cannot_list_own_subdir(entra_writer_sftp, container_cleanup):
    rel = f"entra-writer-nolist-{uuid.uuid4().hex[:8]}"
    entra_writer_sftp.mkdir(f"{WRITE_TREE}/{rel}")
    container_cleanup.append(("dir", f"{TREE_DIR}/{rel}", INBOUND_CONTAINER))
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(f"{WRITE_TREE}/{rel}"))


# ── DENY: the notsftp tree (no group ACE anywhere on it) ────────────────────

def test_cannot_list_notsftp(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(f"{INBOUND_CONTAINER}/notsftp"))


def test_cannot_enter_notsftp(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.chdir(f"{INBOUND_CONTAINER}/notsftp"))


def test_cannot_read_notsftp_file(entra_writer_sftp):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: entra_writer_sftp.getfo(f"{INBOUND_CONTAINER}/notsftp/secret.txt", buf))


# ── DENY: the reader's tree ──────────────────────────────────────────────────
# The headline assertion of the experiment: two principals, no RBAC, mutually
# invisible trees, distinguished only by which group holds an ACE where.

def test_cannot_enter_reader_container(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.chdir(f"/{OUTBOUND_CONTAINER}"))


def test_cannot_list_reader_container(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(f"/{OUTBOUND_CONTAINER}"))


def test_cannot_list_reader_tree(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(f"{OUTBOUND_CONTAINER}/{TREE_DIR}"))


def test_cannot_read_reader_fixture(entra_writer_sftp):
    buf = io.BytesIO()
    assert_sftp_denied(
        lambda: entra_writer_sftp.getfo(f"{OUTBOUND_CONTAINER}/{TREE_DIR}/sample/report.csv", buf)
    )
