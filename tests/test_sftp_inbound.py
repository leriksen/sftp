"""
inbound SFTP permission tests.

Home:        inbound/dev01
Control-plane permission_scope: List only, on the inbound container.
Data-plane ACL: other::-wx on dev01 (access + default) -- write+execute, no read.
Root ACL:    inbound/ -> other::--- (EXPERIMENTAL full deny, see main.tf).

Net effect (assuming the root ACL experiment doesn't break login/traversal
entirely -- see test_can_connect_and_reach_home below): the inbound user can
list its home dir (via permission_scope, not the ACL), create files/dirs
there (via the ACL's write+execute), but cannot read content back, delete
anything, or reach notsftp / the outbound container.
"""
import io
from conftest import assert_sftp_denied, HOME_DIR, INBOUND_CONTAINER, OUTBOUND_CONTAINER


# ── Root-ACL experiment ──────────────────────────────────────────────────────

def test_can_connect_and_reach_home(sftp_inbound_client):
    """If other::--- at the container root breaks the execute-to-traverse
    chain, this is where it shows up: Azure denies before the user can even
    list its own home directory. See the EXPERIMENTAL note on
    azurerm_storage_data_lake_gen2_path.root in main.tf."""
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


# ── ALLOW: list (via container permission_scope, not the ACL) ───────────────

def test_list_home_dir(sftp_inbound_client):
    entries = sftp_inbound_client.listdir(".")
    assert isinstance(entries, list)


def test_list_scratch_dir(sftp_inbound_client, sftp_inbound_artifacts):
    entries = sftp_inbound_client.listdir(sftp_inbound_artifacts["scratch_dir"])
    assert "seed.txt" in entries


# ── DENY: read content (ACL grants write+execute only, no read) ─────────────

def test_cannot_read_own_file(sftp_inbound_client, sftp_inbound_artifacts):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: sftp_inbound_client.getfo(sftp_inbound_artifacts["seed_file"], buf))


# ── DENY: delete (no delete anywhere in scope) ───────────────────────────────

def test_cannot_delete_file(sftp_inbound_client, sftp_inbound_artifacts):
    assert_sftp_denied(lambda: sftp_inbound_client.remove(sftp_inbound_artifacts["seed_file"]))


def test_cannot_delete_dir(sftp_inbound_client, sftp_inbound_artifacts):
    assert_sftp_denied(lambda: sftp_inbound_client.rmdir(sftp_inbound_artifacts["scratch_dir"]))


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
