"""Reader-side Entra SFTP permission tests (storage account "02").

Principal:  service principal in the sftp-entra-readers group.
RBAC:       none. Every allow and deny below is decided by a named group ACE.
ACL:        outbound/                     access group:readers::--x
            outbound/dev01                access group:readers::r-x, default ::r-x
            outbound/dev01/sample[/nested] access group:readers::r-x, default ::r-x
            everything else               no ACE for this group at all

Mirrors what `other::r-x` gives sftpuser1 on account "01", against the same
fixture files (blobs.tf seeds both accounts identically). The fixtures are
Terraform-owned: this principal has no write access anywhere on the account.
"""
import io

from conftest import (
    INBOUND_CONTAINER,
    OUTBOUND_CONTAINER,
    READ_TREE,
    TREE_DIR,
    assert_sftp_denied,
)


# ── ALLOW: list / read ───────────────────────────────────────────────────────

def test_can_connect_and_list_read_tree(entra_reader_sftp):
    entries = entra_reader_sftp.listdir(READ_TREE)
    assert "sample" in entries


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


# ── DENY: the notsftp tree ───────────────────────────────────────────────────
# Worth contrasting with tests/test_aad_rbac.py::test_can_read_notsftp_via_rbac
# on account "01": there, an RBAC-holding principal reads notsftp straight
# through the deny ACL, because a role assignment can't be narrowed by an ACE.
# Here there is no role assignment, so the ACL is the whole story.

def test_cannot_list_notsftp(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.listdir(f"{OUTBOUND_CONTAINER}/notsftp"))


def test_cannot_read_notsftp_file(entra_reader_sftp):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: entra_reader_sftp.getfo(f"{OUTBOUND_CONTAINER}/notsftp/secret.txt", buf))


# ── DENY: the writer's tree ──────────────────────────────────────────────────

def test_cannot_enter_writer_container(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.chdir(f"/{INBOUND_CONTAINER}"))


def test_cannot_list_writer_container(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.listdir(f"/{INBOUND_CONTAINER}"))


def test_cannot_list_writer_tree(entra_reader_sftp):
    assert_sftp_denied(lambda: entra_reader_sftp.listdir(f"{INBOUND_CONTAINER}/{TREE_DIR}"))


def test_cannot_write_to_writer_tree(entra_reader_sftp):
    assert_sftp_denied(
        lambda: entra_reader_sftp.putfo(
            io.BytesIO(b"x"), f"{INBOUND_CONTAINER}/{TREE_DIR}/entra-reader-denied.txt", confirm=False
        )
    )
