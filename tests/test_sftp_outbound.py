"""
outbound SFTP permission tests.

Home:        outbound/dev01
Control-plane permission_scope: List only, on the outbound container.
Data-plane ACL: other::r-x on dev01 (access + default) -- read+execute, no write.
Fixtures:    dev01/sample/{report.csv,notes.txt,nested/extra.txt}, admin-owned
             (azurerm_storage_data_lake_gen2_path.outbound_sample* /
             azurerm_storage_blob.outbound_sample_* in main.tf) -- the
             outbound user has no write access anywhere, so these are seeded
             out-of-band by Terraform rather than by the user itself.
"""
import io
from conftest import assert_sftp_denied, INBOUND_CONTAINER, OUTBOUND_CONTAINER


# ── ALLOW: list / read ───────────────────────────────────────────────────────

def test_list_home_dir(sftp_outbound_client):
    entries = sftp_outbound_client.listdir(".")
    assert "sample" in entries


def test_list_sample_dir(sftp_outbound_client):
    entries = sftp_outbound_client.listdir("sample")
    assert "report.csv" in entries
    assert "notes.txt" in entries
    assert "nested" in entries


def test_list_nested_dir(sftp_outbound_client):
    entries = sftp_outbound_client.listdir("sample/nested")
    assert "extra.txt" in entries


def test_read_report_csv(sftp_outbound_client):
    buf = io.BytesIO()
    sftp_outbound_client.getfo("sample/report.csv", buf)
    assert buf.getvalue() == b"id,value\n1,42\n2,7\n"


def test_read_notes_txt(sftp_outbound_client):
    buf = io.BytesIO()
    sftp_outbound_client.getfo("sample/notes.txt", buf)
    assert buf.getvalue() == b"sample outbound fixture data\n"


def test_read_nested_file(sftp_outbound_client):
    buf = io.BytesIO()
    sftp_outbound_client.getfo("sample/nested/extra.txt", buf)
    assert buf.getvalue() == b"nested fixture data\n"


# ── DENY: write ──────────────────────────────────────────────────────────────

def test_cannot_upload_file(sftp_outbound_client):
    assert_sftp_denied(lambda: sftp_outbound_client.putfo(io.BytesIO(b"x"), "sample/outbound-denied.txt"))


def test_cannot_create_dir(sftp_outbound_client):
    assert_sftp_denied(lambda: sftp_outbound_client.mkdir("sample/outbound-denied-dir"))


# ── DENY: delete ─────────────────────────────────────────────────────────────

def test_cannot_delete_file(sftp_outbound_client):
    assert_sftp_denied(lambda: sftp_outbound_client.remove("sample/report.csv"))


# ── DENY: reach notsftp ──────────────────────────────────────────────────────

def test_cannot_list_notsftp(sftp_outbound_client):
    assert_sftp_denied(lambda: sftp_outbound_client.listdir("../notsftp"))


def test_cannot_read_notsftp_file(sftp_outbound_client):
    buf = io.BytesIO()
    assert_sftp_denied(lambda: sftp_outbound_client.getfo("../notsftp/secret.txt", buf))


# ── DENY: reach the inbound container (see note in test_sftp_inbound.py) ────

def test_cannot_list_inbound_container(sftp_outbound_client):
    assert_sftp_denied(lambda: sftp_outbound_client.listdir(f"/{INBOUND_CONTAINER}"))
