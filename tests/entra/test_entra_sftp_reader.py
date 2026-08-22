"""Reader-side Entra SFTP permission tests (storage account "02").

Principal:  service principal in the sftp-entra-readers group.
RBAC:       none. Every allow and deny below is decided by a named group ACE.
ACL:        sftp/                            access group:readers::--x
            sftp/outbound                    access group:readers::--x
            sftp/outbound/dev01              access group:readers::r-x, default ::r-x
            sftp/outbound/dev01/sample[/nested]  same
            everything else                  no ACE for this group at all

Mirrors what `other::r-x` gives sftpuser1 on account "01", against the same
fixture files at the same tree-relative paths -- the only difference is that on
"01" they sit in their own `outbound` container, and here they sit in a subtree
of a container the writer is also using. The fixtures are Terraform-owned: this
principal has no write access anywhere on the account.
"""
import io

from conftest import (
    NOTSFTP,
    READ_DIR,
    READ_TREE,
    SFTP_ROOT,
    WRITE_DIR,
    WRITE_TREE,
    assert_sftp_denied,
)


# ── ALLOW: list / read ───────────────────────────────────────────────────────

def test_can_connect_and_list_read_tree(entra_reader_sftp):
    entries = entra_reader_sftp.listdir(READ_TREE)
    assert "sample" in entries


def test_can_traverse_to_read_tree(entra_reader_sftp):
    """`--x` on sftp/ and sftp/outbound is enough to walk down, without either
    intermediate directory being listable."""
    try:
        entra_reader_sftp.chdir(READ_TREE)
        assert entra_reader_sftp.getcwd() == READ_TREE
    finally:
        # The client is session-scoped; leave the cwd where every other test
        # expects to find it.
        entra_reader_sftp.chdir("/")


def test_list_sample_dir(entra_reader_sftp):
    entries = entra_reader_sftp.listdir(f"{READ_TREE}/sample")
    assert "report.csv" in entries
    assert "notes.txt" in entries
    assert "nested" in entries


def test_list_nested_dir(entra_reader_sftp):
    entries = entra_reader_sftp.listdir(f"{READ_TREE}/sample/nested")
    assert "extra.txt" in entries


def test_read_report_csv(entra_reader_sftp):
    buf = io.BytesIO()
    entra_reader_sftp.getfo(f"{READ_TREE}/sample/report.csv", buf)
    assert buf.getvalue() == b"id,value\n1,42\n2,7\n"


def test_read_notes_txt(entra_reader_sftp):
    buf = io.BytesIO()
    entra_reader_sftp.getfo(f"{READ_TREE}/sample/notes.txt", buf)
    assert buf.getvalue() == b"sample outbound fixture data\n"


def test_read_nested_file(entra_reader_sftp):
    buf = io.BytesIO()
    entra_reader_sftp.getfo(f"{READ_TREE}/sample/nested/extra.txt", buf)
    assert buf.getvalue() == b"nested fixture data\n"


# ── DENY: write / delete (r-x carries no `w`) ───────────────────────────────

def test_cannot_upload_file(entra_reader_sftp):
    assert_sftp_denied(
        lambda: entra_reader_sftp.putfo(io.BytesIO(b"x"), f"{READ_TREE}/sample/entra-reader-denied.txt")
    )


def test_cannot_create_dir(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.mkdir(f"{READ_TREE}/sample/entra-reader-denied-dir"))


def test_cannot_delete_file(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.remove(f"{READ_TREE}/sample/report.csv"))


# ── DENY: enumerate the shared container ────────────────────────────────────
# `--x` grants traverse, not read, so the reader cannot list the container root
# and discover that `inbound` -- the writer's subtree -- is there at all.

def test_cannot_list_shared_container_root(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.listdir(SFTP_ROOT))


def test_cannot_list_own_intermediate_dir(entra_reader_sftp):
    """The reader's own `outbound` parent is traverse-only: the read grant
    starts one level down, on dev01."""
    assert_sftp_denied(lambda: entra_reader_sftp.listdir(f"{SFTP_ROOT}/{READ_DIR}"))


# ── DENY: the notsftp tree ───────────────────────────────────────────────────
# Worth contrasting with tests/test_aad_rbac.py::test_can_read_notsftp_via_rbac
# on account "01": there, an RBAC-holding principal reads notsftp straight
# through the deny ACL, because a role assignment can't be narrowed by an ACE.
# Here there is no role assignment, so the ACL is the whole story.

def test_cannot_list_notsftp(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.listdir(f"{SFTP_ROOT}/{NOTSFTP}"))


def test_cannot_read_notsftp_file(entra_reader_sftp):
    buf = io.BytesIO()
    assert_sftp_denied(
        lambda: entra_reader_sftp.getfo(f"{SFTP_ROOT}/{NOTSFTP}/secret.txt", buf)
    )


# ── DENY: the writer's subtree, in the same container ───────────────────────
# The reverse half of the headline assertion. Nothing but the absence of a
# named ACE stands between these two principals -- no container boundary, no
# separate account, no RBAC.

def test_cannot_enter_writer_subtree(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.chdir(f"{SFTP_ROOT}/{WRITE_DIR}"))


def test_cannot_list_writer_subtree(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.listdir(f"{SFTP_ROOT}/{WRITE_DIR}"))


def test_cannot_list_writer_tree(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.listdir(WRITE_TREE))


def test_cannot_write_to_writer_tree(entra_reader_sftp):
    assert_sftp_denied(
        lambda: entra_reader_sftp.putfo(
            io.BytesIO(b"x"), f"{WRITE_TREE}/entra-reader-denied.txt", confirm=False
        )
    )
