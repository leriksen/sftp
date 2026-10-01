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

# One container. Each SFTP local user is homed at a "sterling" dir under
# dev01/{inbound,outbound}; every directory above the homes is other::--x
# (traverse only), the homes are other::rwx + user::rwx with matching
# default entries. See sa.tf for the full ACL scheme -- including why the two
# users are NOT isolated from each other (other:: is shared by every local
# user), which test_sftp_overlap.py asserts explicitly.
CONTAINER     = "sftp-test"
INBOUND_HOME  = "dev01/inbound/sterling"
OUTBOUND_HOME = "dev01/outbound/sterling"

# Container-relative paths of every directory above the homes ("" is the
# container root). Neither user may list, read or create anything in these.
TRAVERSE_ONLY_DIRS = ["", "dev01", "dev01/inbound", "dev01/outbound"]


def sftp_path(rel):
    """Absolute SFTP path for a container-relative path. A local user's SFTP
    root "/" is its home *container*, not the account (the server reports
    the inbound home as /dev01/inbound/sterling), so no container prefix.
    Session-scoped clients must only ever be given absolute paths: one chdir
    would silently re-root every relative path in every later test."""
    return f"/{rel}"

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
    (azurerm_role_assignment.tf_executor_blob_owner in rbac.tf)."""
    return _client(
        os.environ["ARM_CLIENT_ID"],
        os.environ["ARM_CLIENT_SECRET"],
    )


def assert_sftp_denied(fn):
    """The operation must fail for lack of permission. A not-found error
    doesn't count: a wrong path would otherwise pass every deny test."""
    with pytest.raises(OSError) as exc_info:
        fn()
    assert not isinstance(exc_info.value, FileNotFoundError), (
        f"failed with not-found, not a permission denial: {exc_info.value}"
    )


def _sftp_connect(username, key_file):
    key = paramiko.RSAKey.from_private_key_file(key_file)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=SFTP_HOST, port=22, username=username, pkey=key)
    return ssh.open_sftp(), ssh


# Local users are literally named "sftpuser<sequence_number>"
# (terraform-azurerm-sftp-local-users names by sequence_number, not a custom
# string) -- inbound/outbound is carried by home_directory, not the login
# name. See sftp.tf/variables.tf.
USERS = {
    "inbound":  {"login": "sftpuser0", "key_env": "SFTP_INBOUND_KEY_FILE",  "home": INBOUND_HOME,  "other_home": OUTBOUND_HOME},
    "outbound": {"login": "sftpuser1", "key_env": "SFTP_OUTBOUND_KEY_FILE", "home": OUTBOUND_HOME, "other_home": INBOUND_HOME},
}


def _connect_user(name):
    u = USERS[name]
    return _sftp_connect(f"{STORAGE_ACCOUNT}.{u['login']}", os.environ[u["key_env"]])


class SftpUser:
    def __init__(self, name, client):
        self.name       = name
        self.client     = client
        self.home       = USERS[name]["home"]        # container-relative
        self.other_home = USERS[name]["other_home"]  # container-relative


@pytest.fixture(scope="session", params=list(USERS))
def user(request):
    """Session-scoped connection for each local user in turn. Absolute paths
    only (see sftp_path) -- never chdir on this client."""
    sftp, ssh = _connect_user(request.param)
    yield SftpUser(request.param, sftp)
    sftp.close()
    ssh.close()


@pytest.fixture
def fresh_sftp():
    """Factory for a brand-new connection that lands in the user's home dir,
    for tests that chdir or use relative paths. Closed after the test, so
    the cwd can't leak into any other test."""
    opened = []

    def _open(name):
        sftp, ssh = _connect_user(name)
        opened.append((sftp, ssh))
        return sftp

    yield _open
    for sftp, ssh in opened:
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
        try:
            if kind == "file":
                fs.get_file_client(path).delete_file()
            else:
                fs.get_directory_client(path).delete_directory()
        except ResourceNotFoundError:
            pass  # the test deleted it itself over SFTP
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

    Not a pytest fixture: it must only run once every pytest session
    touching this account has finished, so it is invoked via
    sweep_artifacts.py at the end of run_sftp_tests.sh.
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
def admin_seed(admin_client):
    """Admin places one file in each traverse-only dir, so the "cannot read"
    tests target a file that demonstrably exists -- a denial on a missing
    path would pass for the wrong reason. Removed again at session end."""
    run_id = uuid.uuid4().hex[:8]
    fs = admin_client.get_file_system_client(CONTAINER)
    seeded = {}
    for d in TRAVERSE_ONLY_DIRS:
        rel = f"{d}/admin-seed-{run_id}.txt" if d else f"admin-seed-{run_id}.txt"
        fs.get_file_client(rel).upload_data(b"admin only", overwrite=True)
        _log_created(CONTAINER, "file", rel)
        seeded[d] = rel
    yield seeded
    for rel in seeded.values():
        fs.get_file_client(rel).delete_file()
        _log_deleted(CONTAINER, "file", rel)


def pytest_collection_modifyitems(items):
    order = ["test_sftp_home", "test_sftp_traverse_only", "test_sftp_overlap"]

    def sort_key(item):
        for i, name in enumerate(order):
            if name in item.nodeid:
                return i
        return len(order)
    items.sort(key=sort_key)
