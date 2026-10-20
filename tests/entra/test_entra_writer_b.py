"""writer_b: read/write access to container-b, no access to container-a.

RBAC: Storage Blob Data Contributor, scoped to container-b only.
ACL:  no entry names writer_b; other::--- on both containers.

Requirement: create and delete files and directories, and cd up and down.
Read comes with it: Entra SFTP refuses cd into a directory without read
(proven live 2026-10-20 with a -wx ACL), so a write-only writer can't
navigate -- hence Contributor rather than a write-only custom role.
"""
import io

from conftest import CONTAINER_A, CONTAINER_B, assert_sftp_denied, rid, sftp_path


def _read(sftp, path):
    buf = io.BytesIO()
    sftp.getfo(path, buf)
    return buf.getvalue()


def _admin_read(admin_client, container, rel):
    return admin_client.get_file_system_client(container).get_file_client(rel).download_file().readall()


# ── ALLOW: write to container-b ──────────────────────────────────────────────

def test_can_upload_file(writer_b, admin_client, container_cleanup):
    rel  = f"writer-upload-{rid()}.txt"
    data = b"from writer_b"
    container_cleanup.append(("file", rel, CONTAINER_B))
    writer_b.putfo(io.BytesIO(data), sftp_path(CONTAINER_B, rel))
    assert _admin_read(admin_client, CONTAINER_B, rel) == data


def test_can_mkdir_and_upload_nested(writer_b, admin_client, container_cleanup):
    top    = f"writer-nest-{rid()}"
    levels = [top, f"{top}/a", f"{top}/a/b"]
    for d in levels:
        container_cleanup.append(("dir", d, CONTAINER_B))
        writer_b.mkdir(sftp_path(CONTAINER_B, d))
        rel = f"{d}/f.txt"
        container_cleanup.append(("file", rel, CONTAINER_B))
        writer_b.putfo(io.BytesIO(rel.encode()), sftp_path(CONTAINER_B, rel))

    for d in levels:
        assert _admin_read(admin_client, CONTAINER_B, f"{d}/f.txt") == f"{d}/f.txt".encode()


def test_can_delete_own_file(writer_b, admin_client, container_cleanup):
    rel = f"writer-delete-{rid()}.txt"
    container_cleanup.append(("file", rel, CONTAINER_B))
    writer_b.putfo(io.BytesIO(b"x"), sftp_path(CONTAINER_B, rel))
    writer_b.remove(sftp_path(CONTAINER_B, rel))
    fs = admin_client.get_file_system_client(CONTAINER_B)
    assert not fs.get_file_client(rel).exists()


def test_can_delete_own_dir(writer_b, admin_client, container_cleanup):
    rel = f"writer-rmdir-{rid()}"
    container_cleanup.append(("dir", rel, CONTAINER_B))
    writer_b.mkdir(sftp_path(CONTAINER_B, rel))
    writer_b.rmdir(sftp_path(CONTAINER_B, rel))
    fs = admin_client.get_file_system_client(CONTAINER_B)
    assert not fs.get_directory_client(rel).exists()


# ── ALLOW: traverse up and down ──────────────────────────────────────────────
# Fresh connections, because these chdir. With a -wx ACL and no RBAC both
# failed on the very first chdir (AuthorizationPermissionMismatch).

def test_can_cd_down_and_up(writer_b, fresh_sftp, container_cleanup):
    top = f"writer-cd-{rid()}"
    for d in (top, f"{top}/a"):
        container_cleanup.append(("dir", d, CONTAINER_B))
        writer_b.mkdir(sftp_path(CONTAINER_B, d))

    sftp = fresh_sftp("writer_b")
    sftp.chdir(sftp_path(CONTAINER_B))
    assert sftp.getcwd() == sftp_path(CONTAINER_B)
    sftp.chdir(top)
    assert sftp.getcwd() == sftp_path(CONTAINER_B, top)
    sftp.chdir("a")
    assert sftp.getcwd() == sftp_path(CONTAINER_B, f"{top}/a")
    sftp.chdir("..")
    assert sftp.getcwd() == sftp_path(CONTAINER_B, top)
    sftp.chdir("..")
    assert sftp.getcwd() == sftp_path(CONTAINER_B)


def test_can_upload_relative_after_cd(writer_b, fresh_sftp, admin_client, container_cleanup):
    """The cwd is usable, not just reported: a relative put lands in it."""
    top = f"writer-cdput-{rid()}"
    container_cleanup.append(("dir", top, CONTAINER_B))
    writer_b.mkdir(sftp_path(CONTAINER_B, top))
    container_cleanup.append(("file", f"{top}/f.txt", CONTAINER_B))

    sftp = fresh_sftp("writer_b")
    sftp.chdir(sftp_path(CONTAINER_B, top))
    sftp.putfo(io.BytesIO(b"relative"), "f.txt")
    assert _admin_read(admin_client, CONTAINER_B, f"{top}/f.txt") == b"relative"


# ── ALLOW: list and read container-b ─────────────────────────────────────────

def test_can_list_container_b(writer_b, seeds):
    s = seeds[CONTAINER_B]
    entries = writer_b.listdir(sftp_path(CONTAINER_B))
    assert s.file in entries
    assert s.nested_dir in entries


def test_can_read_seeded_file_in_container_b(writer_b, seeds):
    s = seeds[CONTAINER_B]
    assert _read(writer_b, sftp_path(CONTAINER_B, s.file)) == s.content
    assert _read(writer_b, sftp_path(CONTAINER_B, s.nested_file)) == s.content


def test_can_read_back_own_upload(writer_b, container_cleanup):
    rel = f"writer-readback-{rid()}.txt"
    container_cleanup.append(("file", rel, CONTAINER_B))
    writer_b.putfo(io.BytesIO(b"readback"), sftp_path(CONTAINER_B, rel))
    assert _read(writer_b, sftp_path(CONTAINER_B, rel)) == b"readback"


def test_can_list_own_subdir(writer_b, container_cleanup):
    top = f"writer-list-{rid()}"
    container_cleanup.append(("dir", top, CONTAINER_B))
    writer_b.mkdir(sftp_path(CONTAINER_B, top))
    container_cleanup.append(("file", f"{top}/f.txt", CONTAINER_B))
    writer_b.putfo(io.BytesIO(b"x"), sftp_path(CONTAINER_B, f"{top}/f.txt"))
    assert writer_b.listdir(sftp_path(CONTAINER_B, top)) == ["f.txt"]


# ── DENY: everything in container-a ──────────────────────────────────────────

def test_cannot_list_container_a(writer_b, seeds):
    assert_sftp_denied(lambda: writer_b.listdir(sftp_path(CONTAINER_A)))


def test_cannot_read_file_in_container_a(writer_b, seeds):
    s = seeds[CONTAINER_A]
    assert_sftp_denied(lambda: _read(writer_b, sftp_path(CONTAINER_A, s.file)))


def test_cannot_read_nested_file_in_container_a(writer_b, seeds):
    s = seeds[CONTAINER_A]
    assert_sftp_denied(lambda: _read(writer_b, sftp_path(CONTAINER_A, s.nested_file)))


def test_cannot_upload_to_container_a(writer_b, seeds, container_cleanup):
    rel = f"writer-denied-{rid()}.txt"
    container_cleanup.append(("file", rel, CONTAINER_A))  # in case it is wrongly allowed
    assert_sftp_denied(lambda: writer_b.putfo(
        io.BytesIO(b"x"), sftp_path(CONTAINER_A, rel), confirm=False))


def test_cannot_overwrite_file_in_container_a(writer_b, seeds):
    s = seeds[CONTAINER_A]
    assert_sftp_denied(lambda: writer_b.putfo(
        io.BytesIO(b"x"), sftp_path(CONTAINER_A, s.file), confirm=False))


def test_cannot_mkdir_in_container_a(writer_b, seeds, container_cleanup):
    rel = f"writer-denied-{rid()}"
    container_cleanup.append(("dir", rel, CONTAINER_A))  # in case it is wrongly allowed
    assert_sftp_denied(lambda: writer_b.mkdir(sftp_path(CONTAINER_A, rel)))


def test_cannot_delete_file_in_container_a(writer_b, seeds):
    s = seeds[CONTAINER_A]
    assert_sftp_denied(lambda: writer_b.remove(sftp_path(CONTAINER_A, s.file)))
