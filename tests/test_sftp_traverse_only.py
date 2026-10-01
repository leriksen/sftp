"""
Traverse-only directory tests, run once per SFTP local user.

Directories: the container root, dev01, dev01/inbound, dev01/outbound
ACL:         other::--x -- execute (traverse) only, no read, no write.

Requirement covered: both users can navigate down to their home dirs, but
cannot create or read files in /, /dev01, /dev01/inbound or /dev01/outbound.
The read tests target a file the admin seeded in each directory
(admin_seed), so a denial can't pass merely because the path is missing.
"""
import io
import uuid

import pytest

from conftest import CONTAINER, TRAVERSE_ONLY_DIRS, assert_sftp_denied, sftp_path

DIR_IDS = ["root" if d == "" else d.replace("/", "-") for d in TRAVERSE_ONLY_DIRS]


def _child(d, name):
    return f"{d}/{name}" if d else name


# ── ALLOW: navigate down to home ─────────────────────────────────────────────

def test_can_cd_to_home_absolute(user, fresh_sftp):
    sftp = fresh_sftp(user.name)
    sftp.chdir(sftp_path(user.home))
    assert isinstance(sftp.listdir("."), list)


# other::--x lets a path pass THROUGH these dirs but not stop AT them: cd
# stats its target, and Azure denies stat on a dir without `r`. So the home
# is reachable only by a path that ends there (absolute, or relative like
# ../../<x>/sterling), never by stepping down one level at a time. Granting
# r-x here would allow stepping, at the cost of letting both users list
# these dirs' entries.

@pytest.mark.parametrize("d", TRAVERSE_ONLY_DIRS, ids=DIR_IDS)
def test_cannot_cd_into(user, d, fresh_sftp):
    sftp = fresh_sftp(user.name)
    assert_sftp_denied(lambda: sftp.chdir(sftp_path(d)))


# ── DENY: list ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("d", TRAVERSE_ONLY_DIRS, ids=DIR_IDS)
def test_cannot_list(user, d):
    assert_sftp_denied(lambda: user.client.listdir(sftp_path(d)))


# ── DENY: read an existing file ──────────────────────────────────────────────

@pytest.mark.parametrize("d", TRAVERSE_ONLY_DIRS, ids=DIR_IDS)
def test_cannot_read_file(user, d, admin_seed):
    assert_sftp_denied(lambda: user.client.getfo(sftp_path(admin_seed[d]), io.BytesIO()))


# ── DENY: create a file ──────────────────────────────────────────────────────

@pytest.mark.parametrize("d", TRAVERSE_ONLY_DIRS, ids=DIR_IDS)
def test_cannot_create_file(user, d, admin_client, container_cleanup):
    rel = _child(d, f"denied-{uuid.uuid4().hex[:8]}.txt")
    container_cleanup.append(("file", rel, CONTAINER))  # only if it leaks through
    assert_sftp_denied(lambda: user.client.putfo(io.BytesIO(b"x"), sftp_path(rel)))
    assert not admin_client.get_file_system_client(CONTAINER).get_file_client(rel).exists()


# ── DENY: create a directory ─────────────────────────────────────────────────

@pytest.mark.parametrize("d", TRAVERSE_ONLY_DIRS, ids=DIR_IDS)
def test_cannot_create_dir(user, d, admin_client, container_cleanup):
    rel = _child(d, f"denied-{uuid.uuid4().hex[:8]}")
    container_cleanup.append(("dir", rel, CONTAINER))  # only if it leaks through
    assert_sftp_denied(lambda: user.client.mkdir(sftp_path(rel)))
    assert not admin_client.get_file_system_client(CONTAINER).get_directory_client(rel).exists()


# ── DENY: delete an existing file ────────────────────────────────────────────

@pytest.mark.parametrize("d", TRAVERSE_ONLY_DIRS, ids=DIR_IDS)
def test_cannot_delete_file(user, d, admin_client, admin_seed):
    assert_sftp_denied(lambda: user.client.remove(sftp_path(admin_seed[d])))
    assert admin_client.get_file_system_client(CONTAINER).get_file_client(admin_seed[d]).exists()
