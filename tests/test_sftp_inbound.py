"""
inbound SFTP permission tests.

Home:        inbound/dev01
Control-plane permission_scope: none -- ACL permission to the home directory
             alone is sufficient to connect (see main.tf).
Data-plane ACL: dev01 access = other::rwx + user::rwx (unnamed owner entry);
             default = other::-wx + user::-wx. inbound becomes the owner of
             whatever it creates (Azure assigns owner: "lu-<userId>" to new
             SFTP uploads), so both entries matter -- see the note on
             module.adls_filesystem in main.tf.
Root ACL:    inbound/ -> other::--x (traverse-only; other::--- was tried and
             confirmed to break every ACL-gated operation in the container).

Net effect: the inbound user can list its home dir, create files/dirs there,
and delete anything within its own home dir (POSIX bundles "create" and
"delete" into the directory's `w` bit -- there's no way to grant create-only
without also allowing delete), but cannot read content back, and cannot
reach notsftp / the outbound container.
"""
import io
import uuid

from conftest import assert_sftp_denied, HOME_DIR, INBOUND_CONTAINER, OUTBOUND_CONTAINER


def test_can_connect_and_reach_home(sftp_inbound_client):
    entries = sftp_inbound_client.listdir(".")
    assert isinstance(entries, list)


# ── ALLOW: create / write ────────────────────────────────────────────────────

def test_upload_file(sftp_inbound_client, sftp_inbound_artifacts, admin_client, container_cleanup):
    rel = f"{sftp_inbound_artifacts['scratch_dir']}/inbound-upload.txt"
    # confirm=False: the ACL grants write+execute but not read, and putfo's
    # default post-upload stat needs read.
    sftp_inbound_client.putfo(io.BytesIO(b"inbound data"), rel, confirm=False)
    container_cleanup.append(("file", f"{HOME_DIR}/{rel}", INBOUND_CONTAINER))
    # inbound can't read back what it wrote -- verify out-of-band via admin.
    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    fc = fs.get_file_client(f"{HOME_DIR}/{rel}")
    assert fc.exists()
    assert fc.download_file().readall() == b"inbound data"


def test_create_subdir(sftp_inbound_client, sftp_inbound_artifacts, admin_client, container_cleanup):
    rel = f"{sftp_inbound_artifacts['scratch_dir']}/inbound-subdir"
    sftp_inbound_client.mkdir(rel)
    container_cleanup.append(("dir", f"{HOME_DIR}/{rel}", INBOUND_CONTAINER))
    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    assert fs.get_directory_client(f"{HOME_DIR}/{rel}").exists()


# ── ALLOW: list the home dir itself (via the ACL's `r`, not permission_scope) ─

def test_list_home_dir(sftp_inbound_client):
    entries = sftp_inbound_client.listdir(".")
    assert isinstance(entries, list)


# ── DENY: list into subdirectories it creates -- only the home dir itself
#          (dev01's access ACE) has `r`; anything created within inherits
#          the default ACE (-wx, no `r`), consistent with the "push/write
#          only, no readback" semantics applying uniformly to both file
#          content and nested directory listings. ────────────────────────────

def test_cannot_list_scratch_dir(sftp_inbound_client, sftp_inbound_artifacts):
    assert_sftp_denied(lambda: sftp_inbound_client.listdir(sftp_inbound_artifacts["scratch_dir"]))


# ── DENY: read content (ACL grants write+execute only, no read) ─────────────

def test_cannot_read_own_file(sftp_inbound_client, sftp_inbound_artifacts):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: sftp_inbound_client.getfo(sftp_inbound_artifacts["seed_file"], buf))


# ── ALLOW: delete within its own home dir ────────────────────────────────────
# POSIX bundles "create" and "delete" into the same directory `w` bit -- there
# is no ACL-level way to grant inbound create-only without also allowing it
# to delete anything within dev01. This is the scheme's actual, expected
# shape, not a gap (confirmed via a live test run against dev01's other::rwx
# access ACE).

def test_can_delete_own_file(sftp_inbound_client, admin_client):
    rel = f"delete-probe-{uuid.uuid4().hex[:8]}.txt"
    sftp_inbound_client.putfo(io.BytesIO(b"x"), rel, confirm=False)
    sftp_inbound_client.remove(rel)
    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    assert not fs.get_file_client(f"{HOME_DIR}/{rel}").exists()


def test_can_delete_own_dir(sftp_inbound_client, admin_client):
    rel = f"delete-probe-dir-{uuid.uuid4().hex[:8]}"
    sftp_inbound_client.mkdir(rel)
    sftp_inbound_client.rmdir(rel)
    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    assert not fs.get_directory_client(f"{HOME_DIR}/{rel}").exists()


# ── DENY: reach notsftp ──────────────────────────────────────────────────────

def test_cannot_list_notsftp(sftp_inbound_client):
    assert_sftp_denied(lambda: sftp_inbound_client.listdir("../notsftp"))


def test_cannot_enter_notsftp(sftp_inbound_client):
    assert_sftp_denied(lambda: sftp_inbound_client.chdir("../notsftp"))


def test_cannot_read_notsftp_file(sftp_inbound_client):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: sftp_inbound_client.getfo("../notsftp/secret.txt", buf))


# ── DENY: reach the outbound container ───────────────────────────────────────
# inbound and outbound are separate filesystems/containers, so this should be
# structurally unreachable regardless of ACLs -- kept as an explicit
# regression check rather than an assumption, since a single shared-container
# variant of this exact idea broke isolation in the sibling adls project via
# by-name sibling traversal.

def test_cannot_list_outbound_container(sftp_inbound_client):
    assert_sftp_denied(lambda: sftp_inbound_client.listdir(f"/{OUTBOUND_CONTAINER}"))


def test_cannot_enter_outbound_container(sftp_inbound_client):
    assert_sftp_denied(lambda: sftp_inbound_client.chdir(f"/{OUTBOUND_CONTAINER}"))
