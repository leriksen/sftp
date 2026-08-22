"""Writer-side Entra SFTP permission tests (storage account "02").

Principal:  service principal in the sftp-entra-writers group.
RBAC:       none. Every allow and deny below is decided by a named group ACE.
ACL:        sftp/                access group:writers::--x  (traverse, no read)
            sftp/inbound         access group:writers::--x  (traverse, no read)
            sftp/inbound/dev01   access group:writers::rwx, default ::-wx
            everything else      no ACE for this group at all

`sftp/inbound/dev01` is the deliberate mirror of what `other::` gives sftpuser0
on account "01" -- rwx on the tree root so it can list it, -wx inherited by
everything created inside so content can be pushed but never read back.

What is *not* mirrorable on account "01" is the rest: the reader's subtree lives
in this same container, and the writer is walled out of it by having no ACE
there. `other::` can't express that, because every local user in a container
shares it -- which is why account "01" needs one container per user. The
`sftp/` root grant is `--x` rather than `r-x` precisely so the writer cannot
even list the container root and learn that `outbound` exists.

No home directory: Entra SFTP does not support one, so every path is
container-qualified rather than home-relative.
"""
import io
import uuid

from conftest import (
    NOTSFTP,
    READ_DIR,
    READ_TREE,
    SFTP_CONTAINER,
    SFTP_ROOT,
    WRITE_DIR,
    WRITE_TREE,
    WRITE_TREE_REL,
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


def test_can_traverse_to_write_tree(entra_writer_sftp):
    """`--x` on sftp/ and sftp/inbound is enough to walk down to the tree even
    though neither intermediate directory can be listed."""
    try:
        entra_writer_sftp.chdir(WRITE_TREE)
        assert entra_writer_sftp.getcwd() == WRITE_TREE
    finally:
        # The client is session-scoped; leave the cwd where every other test
        # expects to find it.
        entra_writer_sftp.chdir("/")


# ── ALLOW: create ────────────────────────────────────────────────────────────

def test_upload_file(entra_writer_sftp, admin_client, container_cleanup):
    rel = f"entra-writer-upload-{uuid.uuid4().hex[:8]}.txt"
    # confirm=False: the inherited default ACE grants write+execute but not
    # read, and putfo's default post-upload stat needs read.
    entra_writer_sftp.putfo(io.BytesIO(b"entra writer data"), f"{WRITE_TREE}/{rel}", confirm=False)
    container_cleanup.append(("file", f"{WRITE_TREE_REL}/{rel}", SFTP_CONTAINER))

    # The writer can't read back what it wrote -- verify out-of-band.
    fs = admin_client.get_file_system_client(SFTP_CONTAINER)
    fc = fs.get_file_client(f"{WRITE_TREE_REL}/{rel}")
    assert fc.exists()
    assert fc.download_file().readall() == b"entra writer data"


def test_create_subdir(entra_writer_sftp, admin_client, container_cleanup):
    rel = f"entra-writer-dir-{uuid.uuid4().hex[:8]}"
    entra_writer_sftp.mkdir(f"{WRITE_TREE}/{rel}")
    container_cleanup.append(("dir", f"{WRITE_TREE_REL}/{rel}", SFTP_CONTAINER))
    fs = admin_client.get_file_system_client(SFTP_CONTAINER)
    assert fs.get_directory_client(f"{WRITE_TREE_REL}/{rel}").exists()


# ── ALLOW: delete within its own tree ────────────────────────────────────────
# POSIX bundles create and delete into the directory's `w` bit, so a
# create-only grant isn't expressible here any more than it was on account 01.

def test_can_delete_own_file(entra_writer_sftp, admin_client):
    rel = f"entra-writer-delete-probe-{uuid.uuid4().hex[:8]}.txt"
    entra_writer_sftp.putfo(io.BytesIO(b"x"), f"{WRITE_TREE}/{rel}", confirm=False)
    _log_created(SFTP_CONTAINER, "file", f"{WRITE_TREE_REL}/{rel}")
    entra_writer_sftp.remove(f"{WRITE_TREE}/{rel}")
    _log_deleted(SFTP_CONTAINER, "file", f"{WRITE_TREE_REL}/{rel}")
    fs = admin_client.get_file_system_client(SFTP_CONTAINER)
    assert not fs.get_file_client(f"{WRITE_TREE_REL}/{rel}").exists()


# ── DENY: read back its own content (default ACE is -wx, no `r`) ────────────

def test_cannot_read_own_file(entra_writer_sftp, admin_client, container_cleanup):
    rel = f"entra-writer-readback-{uuid.uuid4().hex[:8]}.txt"
    entra_writer_sftp.putfo(io.BytesIO(b"no readback"), f"{WRITE_TREE}/{rel}", confirm=False)
    container_cleanup.append(("file", f"{WRITE_TREE_REL}/{rel}", SFTP_CONTAINER))
    buf = io.BytesIO()
    assert_sftp_denied(lambda: entra_writer_sftp.getfo(f"{WRITE_TREE}/{rel}", buf))


def test_cannot_list_own_subdir(entra_writer_sftp, container_cleanup):
    rel = f"entra-writer-nolist-{uuid.uuid4().hex[:8]}"
    entra_writer_sftp.mkdir(f"{WRITE_TREE}/{rel}")
    container_cleanup.append(("dir", f"{WRITE_TREE_REL}/{rel}", SFTP_CONTAINER))
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(f"{WRITE_TREE}/{rel}"))


# ── DENY: enumerate the shared container ────────────────────────────────────
# `--x` grants traverse, not read. Without this the writer could list the
# container root, see `outbound`, and learn the reader's tree exists -- the
# subtree boundary would still hold but it would no longer be opaque.

def test_cannot_list_shared_container_root(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(SFTP_ROOT))


def test_cannot_list_own_intermediate_dir(entra_writer_sftp):
    """Even the writer's own `inbound` parent is traverse-only: it holds the
    grant one level down, on dev01."""
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(f"{SFTP_ROOT}/{WRITE_DIR}"))


# ── DENY: the notsftp tree (no group ACE anywhere on it) ────────────────────

def test_cannot_list_notsftp(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(f"{SFTP_ROOT}/{NOTSFTP}"))


def test_cannot_enter_notsftp(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.chdir(f"{SFTP_ROOT}/{NOTSFTP}"))


def test_cannot_read_notsftp_file(entra_writer_sftp):
    buf = io.BytesIO()
    assert_sftp_denied(
        lambda: entra_writer_sftp.getfo(f"{SFTP_ROOT}/{NOTSFTP}/secret.txt", buf)
    )


# ── DENY: the reader's subtree, in the same container ───────────────────────
# The headline assertion of the experiment. Two principals, one container, no
# RBAC, mutually invisible subtrees -- distinguished only by which group holds
# an ACE where. Account "01" cannot express this at all: `other::` is shared by
# every local user in a container, so its isolation has to be drawn at the
# container boundary instead.

def test_cannot_enter_reader_subtree(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.chdir(f"{SFTP_ROOT}/{READ_DIR}"))


def test_cannot_list_reader_subtree(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(f"{SFTP_ROOT}/{READ_DIR}"))


def test_cannot_list_reader_tree(entra_writer_sftp):
    assert_sftp_denied(lambda: entra_writer_sftp.listdir(READ_TREE))


def test_cannot_read_reader_fixture(entra_writer_sftp):
    buf = io.BytesIO()
    assert_sftp_denied(
        lambda: entra_writer_sftp.getfo(f"{READ_TREE}/sample/report.csv", buf)
    )


def test_cannot_write_to_reader_tree(entra_writer_sftp):
    """Same container, so this is reachable by name -- it is the ACL, not a
    container boundary, that stops it."""
    assert_sftp_denied(
        lambda: entra_writer_sftp.putfo(
            io.BytesIO(b"x"), f"{READ_TREE}/sample/entra-writer-denied.txt", confirm=False
        )
    )
