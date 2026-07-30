import io
import json
import os
import uuid
import paramiko
import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import ClientSecretCredential
from azure.storage.filedatalake import DataLakeFileClient, DataLakeServiceClient

TENANT_ID       = os.environ["AZURE_TENANT_ID"]
STORAGE_ACCOUNT = os.environ["SFTP_STORAGE_ACCOUNT"]
ACCOUNT_URL     = f"https://{STORAGE_ACCOUNT}.dfs.core.windows.net"
SFTP_HOST       = f"{STORAGE_ACCOUNT}.blob.core.windows.net"

# Each SFTP local user is homed at <container>/dev01. inbound gets
# other::-wx on dev01 (write+execute, no read) layered on top of a
# list-only container permission_scope; outbound gets other::r-x
# (read+execute, no write). See main.tf for the full ACL scheme, including
# the notsftp deny tree and the experimental container-root other::---.
INBOUND_CONTAINER  = "inbound"
OUTBOUND_CONTAINER = "outbound"
HOME_DIR            = "dev01"

# Durable ledger of artifacts the test harness itself creates, so the
# safety-net sweep (sweep_leftover_artifacts, below) can delete exactly
# those and never anything pre-existing in the storage account -- letting
# these tests run safely against an account that already holds real data.
# In-memory tracking alone wouldn't survive a crashed/killed run, hence a
# file on disk rather than a plain list.
_TESTS_DIR  = os.path.dirname(os.path.abspath(__file__))
CREATED_LOG = os.path.join(_TESTS_DIR, ".artifacts_created.jsonl")
DELETED_LOG = os.path.join(_TESTS_DIR, ".artifacts_deleted.jsonl")


def _log_artifact(log_path, container, kind, path):
    with open(log_path, "a") as f:
        f.write(json.dumps({"container": container, "kind": kind, "path": path}) + "\n")


def _log_created(container, kind, path):
    _log_artifact(CREATED_LOG, container, kind, path)


def _log_deleted(container, kind, path):
    _log_artifact(DELETED_LOG, container, kind, path)


def _read_log(log_path):
    if not os.path.exists(log_path):
        return []
    with open(log_path) as f:
        return [json.loads(line) for line in f if line.strip()]


# ── Per-test transfer-size instrumentation for the HTML/JUnit reports ───────
# Wraps the SFTP/DataLake SDK calls once here rather than touching every
# test body. Attribution to "the currently running test" is via a single
# module-level nodeid (pytest runs this suite's tests sequentially within a
# session, so there's no concurrency to race).
_CURRENT_NODEID = None
_TRANSFER_STATS = {}


def _record_transfer(direction, nbytes):
    if _CURRENT_NODEID is None or nbytes is None:
        return
    stats = _TRANSFER_STATS.setdefault(_CURRENT_NODEID, {"sent": 0, "received": 0})
    stats[direction] += nbytes


_orig_putfo = paramiko.SFTPClient.putfo


def _tracked_putfo(self, fl, remotepath, *args, **kwargs):
    start = fl.tell()
    fl.seek(0, io.SEEK_END)
    size = fl.tell() - start
    fl.seek(start)
    result = _orig_putfo(self, fl, remotepath, *args, **kwargs)
    _record_transfer("sent", size)
    return result


paramiko.SFTPClient.putfo = _tracked_putfo

_orig_getfo = paramiko.SFTPClient.getfo


def _tracked_getfo(self, remotepath, fl, *args, **kwargs):
    start = fl.tell()
    result = _orig_getfo(self, remotepath, fl, *args, **kwargs)
    _record_transfer("received", fl.tell() - start)
    return result


paramiko.SFTPClient.getfo = _tracked_getfo

_orig_upload_data = DataLakeFileClient.upload_data


def _tracked_upload_data(self, data, *args, **kwargs):
    try:
        size = len(data)
    except TypeError:
        size = None
    result = _orig_upload_data(self, data, *args, **kwargs)
    _record_transfer("sent", size)
    return result


DataLakeFileClient.upload_data = _tracked_upload_data

_orig_download_file = DataLakeFileClient.download_file


def _tracked_download_file(self, *args, **kwargs):
    result = _orig_download_file(self, *args, **kwargs)
    _record_transfer("received", getattr(result, "size", None))
    return result


DataLakeFileClient.download_file = _tracked_download_file


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global _CURRENT_NODEID
    _CURRENT_NODEID = item.nodeid
    yield
    _CURRENT_NODEID = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        filepath, lineno, _ = item.location
        stats = _TRANSFER_STATS.get(item.nodeid, {"sent": 0, "received": 0})
        props = [
            ("source_file", filepath),
            ("source_line", lineno + 1),
            ("bytes_sent", stats["sent"]),
            ("bytes_received", stats["received"]),
        ]
        # Both are needed: pytest-html's row hook reads this call-phase
        # report's own user_properties directly, while pytest's junitxml
        # plugin builds its <properties> from a *separate* teardown-phase
        # report object, freshly copied from item.user_properties at that
        # later point -- so only appending here (report.user_properties)
        # would show up in the HTML but silently vanish from the JUnit XML.
        report.user_properties.extend(props)
        item.user_properties.extend(props)


def pytest_html_results_table_header(cells):
    cells.insert(2, "<th>Source</th>")
    cells.insert(3, "<th>Sent (B)</th>")
    cells.insert(4, "<th>Received (B)</th>")


def pytest_html_results_table_row(report, cells):
    props = dict(report.user_properties)
    source_file = props.get("source_file")
    if source_file:
        rel = os.path.relpath(source_file, _TESTS_DIR)
        link = (
            f'<a href="file://{os.path.abspath(source_file)}" target="_blank">'
            f'{rel}:{props.get("source_line", "")}</a>'
        )
    else:
        link = ""
    cells.insert(2, f"<td>{link}</td>")
    cells.insert(3, f"<td>{props.get('bytes_sent', '')}</td>")
    cells.insert(4, f"<td>{props.get('bytes_received', '')}</td>")


def _client(client_id, client_secret):
    cred = ClientSecretCredential(
        tenant_id=TENANT_ID,
        client_id=client_id,
        client_secret=client_secret,
    )
    return DataLakeServiceClient(account_url=ACCOUNT_URL, credential=cred)


@pytest.fixture(scope="session")
def admin_client():
    """Terraform executor SP -- has Storage Blob Data Owner
    (azurerm_role_assignment.tf_executor_blob_owner in main.tf)."""
    return _client(
        os.environ["ARM_CLIENT_ID"],
        os.environ["ARM_CLIENT_SECRET"],
    )


@pytest.fixture(scope="session")
def aad_reader_client():
    """Client-credential SP standing in for the ADLS_Reader AAD group
    (azurerm_role_assignment.aad_reader in main.tf), reused from the
    sibling adls project."""
    return _client(
        os.environ["AAD_READER_CLIENT_ID"],
        os.environ["AAD_READER_CLIENT_SECRET"],
    )


@pytest.fixture(scope="session")
def aad_writer_client():
    """Client-credential SP standing in for the ADLS_Write AAD group
    (azurerm_role_assignment.aad_writer in main.tf), reused from the
    sibling adls project. Verified empirically before the role assignment
    was added: this SP had zero access (403 AuthorizationPermissionMismatch)
    against this storage account."""
    return _client(
        os.environ["AAD_WRITER_CLIENT_ID"],
        os.environ["AAD_WRITER_CLIENT_SECRET"],
    )


def assert_denied(fn):
    with pytest.raises(HttpResponseError) as exc_info:
        fn()
    assert exc_info.value.status_code == 403, (
        f"Expected 403, got {exc_info.value.status_code}"
    )


def assert_sftp_denied(fn):
    with pytest.raises(OSError):
        fn()


def _sftp_connect(username, key_file):
    key = paramiko.RSAKey.from_private_key_file(key_file)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=SFTP_HOST, port=22, username=username, pkey=key)
    return ssh.open_sftp(), ssh


@pytest.fixture(scope="session")
def sftp_inbound_client():
    # Local user is literally named "sftpuser0" (terraform-azurerm-sftp-local-users
    # names by sequence_number, not a custom string) -- inbound/outbound is
    # carried by home_directory, not the login name. See main.tf/variables.tf.
    sftp, ssh = _sftp_connect(
        f"{STORAGE_ACCOUNT}.sftpuser0",
        os.environ["SFTP_INBOUND_KEY_FILE"],
    )
    yield sftp
    sftp.close()
    ssh.close()


@pytest.fixture(scope="session")
def sftp_outbound_client():
    sftp, ssh = _sftp_connect(
        f"{STORAGE_ACCOUNT}.sftpuser1",
        os.environ["SFTP_OUTBOUND_KEY_FILE"],
    )
    yield sftp
    sftp.close()
    ssh.close()


class _TrackedCreations(list):
    """list that logs every appended (kind, path, container) triple to
    CREATED_LOG as it's added, so sweep_leftover_artifacts can find it even
    if the process is killed before this fixture's own teardown runs."""

    def append(self, item):
        kind, path, container = item
        _log_created(container, kind, path)
        super().append(item)


@pytest.fixture
def container_cleanup(admin_client):
    """Per-test cleanup of exactly the artifacts a test creates.

    A test appends ("file"|"dir", container_relative_path, container) for
    each artifact it creates. After the test the admin removes exactly
    those, in reverse creation order (children before parents).
    """
    created = _TrackedCreations()
    yield created
    for kind, path, container in reversed(created):
        fs = admin_client.get_file_system_client(container)
        if kind == "file":
            fs.get_file_client(path).delete_file()
        else:
            fs.get_directory_client(path).delete_directory()
        _log_deleted(container, kind, path)


def sweep_leftover_artifacts(admin_client):
    """Safety net beyond per-test cleanup: deletes exactly the artifacts the
    test harness itself created and never got around to removing (tracked
    via CREATED_LOG/DELETED_LOG), for the case where a test/fixture's own
    cleanup was skipped by a crashed or killed run. Never touches anything
    else -- pre-existing data in the storage account is always left alone,
    so these tests can run safely against an account that already holds
    real content. Deletes deepest-first so we don't rely on a parent
    directory's delete cascading to remove a leftover child first;
    already-gone descendants are ignored. Resets both logs once reconciled.

    Not a pytest fixture -- run_aad_tests.sh and run_sftp_tests.sh execute
    as separate, concurrently-running pytest sessions under run_tests.sh, so
    a session-scoped autouse fixture here would race: the faster session's
    teardown could sweep away artifacts the slower session still has
    in-flight. Call this only via sweep_artifacts.py, once both sessions
    have fully finished (see run_tests.sh).
    """
    created = _read_log(CREATED_LOG)
    deleted_keys = {(e["container"], e["kind"], e["path"]) for e in _read_log(DELETED_LOG)}
    leftover = [e for e in created if (e["container"], e["kind"], e["path"]) not in deleted_keys]
    leftover.sort(key=lambda e: e["path"].count("/"), reverse=True)

    for e in leftover:
        fs = admin_client.get_file_system_client(e["container"])
        try:
            if e["kind"] == "dir":
                fs.get_directory_client(e["path"]).delete_directory()
            else:
                fs.get_file_client(e["path"]).delete_file()
            print(f"swept leftover: {e['container']}/{e['path']}")
        except ResourceNotFoundError:
            pass

    open(CREATED_LOG, "w").close()
    open(DELETED_LOG, "w").close()


@pytest.fixture(scope="session")
def sftp_inbound_artifacts(sftp_inbound_client, admin_client):
    """inbound user creates a scratch dir + seed file via SFTP; admin removes
    exactly those. putfo(..., confirm=False): the inbound ACL grants
    write+execute but not read, and putfo's default post-upload stat needs
    read."""
    run_id  = uuid.uuid4().hex[:8]
    scratch = f"test-sftp-{run_id}"
    seed    = f"{scratch}/seed.txt"

    sftp_inbound_client.mkdir(scratch)
    _log_created(INBOUND_CONTAINER, "dir", f"{HOME_DIR}/{scratch}")
    sftp_inbound_client.putfo(io.BytesIO(b"hello from inbound"), seed, confirm=False)
    _log_created(INBOUND_CONTAINER, "file", f"{HOME_DIR}/{seed}")

    yield {"scratch_dir": scratch, "seed_file": seed}

    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    fs.get_file_client(f"{HOME_DIR}/{seed}").delete_file()
    _log_deleted(INBOUND_CONTAINER, "file", f"{HOME_DIR}/{seed}")
    fs.get_directory_client(f"{HOME_DIR}/{scratch}").delete_directory()
    _log_deleted(INBOUND_CONTAINER, "dir", f"{HOME_DIR}/{scratch}")


def pytest_collection_modifyitems(items):
    def sort_key(item):
        if "test_sftp_inbound" in item.nodeid:
            return 0
        if "test_sftp_outbound" in item.nodeid:
            return 1
        if "test_notsftp_denied" in item.nodeid:
            return 2
        if "test_aad_rbac" in item.nodeid:
            return 3
        return 4
    items.sort(key=sort_key)
