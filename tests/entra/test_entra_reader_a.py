"""reader_a: read access to container-a, no access to container-b.

RBAC: Storage Blob Data Reader, scoped to container-a only.
ACL:  no entry names reader_a; other::--- on both containers.

The seeds fixture (admin, over REST) provides the files read here; reader_a
can't write anywhere, so it can't create its own.
"""
import io

from conftest import CONTAINER_A, CONTAINER_B, assert_sftp_denied, rid, sftp_path


def _read(sftp, path):
    buf = io.BytesIO()
    sftp.getfo(path, buf)
    return buf.getvalue()


# ── ALLOW: read container-a ──────────────────────────────────────────────────

def test_can_list_container_a(reader_a, seeds):
    s = seeds[CONTAINER_A]
    entries = reader_a.listdir(sftp_path(CONTAINER_A))
    assert s.file in entries
    assert s.nested_dir in entries


def test_can_read_file(reader_a, seeds):
    s = seeds[CONTAINER_A]
    assert _read(reader_a, sftp_path(CONTAINER_A, s.file)) == s.content


def test_can_list_and_read_nested(reader_a, seeds):
    s = seeds[CONTAINER_A]
    assert "nested.txt" in reader_a.listdir(sftp_path(CONTAINER_A, s.nested_dir))
    assert _read(reader_a, sftp_path(CONTAINER_A, s.nested_file)) == s.content


# ── DENY: write to container-a (Reader has no write/delete) ────────────────────────────

def test_cannot_upload_to_container_a(reader_a, seeds, container_cleanup):
    rel = f"reader-denied-{rid()}.txt"
    container_cleanup.append(("file", rel, CONTAINER_A))  # in case it is wrongly allowed
    assert_sftp_denied(lambda: reader_a.putfo(
        io.BytesIO(b"x"), sftp_path(CONTAINER_A, rel)))


def test_cannot_overwrite_file_in_container_a(reader_a, seeds):
    s = seeds[CONTAINER_A]
    assert_sftp_denied(lambda: reader_a.putfo(io.BytesIO(b"x"), sftp_path(CONTAINER_A, s.file)))


def test_cannot_mkdir_in_container_a(reader_a, seeds, container_cleanup):
    rel = f"reader-denied-{rid()}"
    container_cleanup.append(("dir", rel, CONTAINER_A))  # in case it is wrongly allowed
    assert_sftp_denied(lambda: reader_a.mkdir(sftp_path(CONTAINER_A, rel)))


def test_cannot_delete_file_in_container_a(reader_a, seeds):
    s = seeds[CONTAINER_A]
    assert_sftp_denied(lambda: reader_a.remove(sftp_path(CONTAINER_A, s.file)))


# ── DENY: everything in container-b ──────────────────────────────────────────

def test_cannot_list_container_b(reader_a, seeds):
    assert_sftp_denied(lambda: reader_a.listdir(sftp_path(CONTAINER_B)))


def test_cannot_read_file_in_container_b(reader_a, seeds):
    s = seeds[CONTAINER_B]
    assert_sftp_denied(lambda: _read(reader_a, sftp_path(CONTAINER_B, s.file)))


def test_cannot_read_nested_file_in_container_b(reader_a, seeds):
    s = seeds[CONTAINER_B]
    assert_sftp_denied(lambda: _read(reader_a, sftp_path(CONTAINER_B, s.nested_file)))


def test_cannot_upload_to_container_b(reader_a, seeds, container_cleanup):
    rel = f"reader-denied-{rid()}.txt"
    container_cleanup.append(("file", rel, CONTAINER_B))  # in case it is wrongly allowed
    assert_sftp_denied(lambda: reader_a.putfo(
        io.BytesIO(b"x"), sftp_path(CONTAINER_B, rel), confirm=False))


def test_cannot_mkdir_in_container_b(reader_a, seeds, container_cleanup):
    rel = f"reader-denied-{rid()}"
    container_cleanup.append(("dir", rel, CONTAINER_B))  # in case it is wrongly allowed
    assert_sftp_denied(lambda: reader_a.mkdir(sftp_path(CONTAINER_B, rel)))


def test_cannot_delete_file_in_container_b(reader_a, seeds):
    s = seeds[CONTAINER_B]
    assert_sftp_denied(lambda: reader_a.remove(sftp_path(CONTAINER_B, s.file)))
