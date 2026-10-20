"""Fixtures for the Entra ID SFTP suite (storage account "02").

Differs from the account "01" local-user suite in tests/ in four structural
ways:

1. No local users exist on this account (local_user_enabled = false). The
   principals are two Entra service principals created by entra.tf, each
   holding one container-scoped data-plane role (rbac.tf). No ACL entry
   names either; the container ACLs only carry other::---:

     reader_a  Storage Blob Data Reader       container-a   nothing on container-b
     writer_b  Storage Blob Data Contributor  container-b   nothing on container-a

2. Authentication is an OpenSSH certificate, not a bare key. Each SP has its
   own persistent RSA key pair (tests/entra/.entra_<name>_key, made by
   setup_creds.sh). The SP signs in to Entra and `az sftp cert` signs that
   public key; paramiko presents key + certificate. Certificates last 65
   minutes, so they are minted once per session.

3. There is no home directory -- unsupported for Entra principals. Sessions
   land on the account root, so every SFTP path here is absolute and
   container-qualified ("/container-a/..."). Absolute matters: the SFTP
   clients are session-scoped, and one chdir would silently re-root every
   relative path in every later test.

4. The artifact ledger lives in tests/entra/.artifacts_*.jsonl, swept by
   tests/entra/sweep_artifacts.py -- separate from tests/sweep_artifacts.py,
   whose admin client is bound to account "01".
"""
import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass

import paramiko
import pytest
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import ClientSecretCredential
from azure.storage.filedatalake import DataLakeServiceClient

TENANT_ID       = os.environ["AZURE_TENANT_ID"]
STORAGE_ACCOUNT = os.environ["ENTRA_STORAGE_ACCOUNT"]
ACCOUNT_URL     = f"https://{STORAGE_ACCOUNT}.dfs.core.windows.net"
SFTP_HOST       = f"{STORAGE_ACCOUNT}.blob.core.windows.net"

CONTAINER_A = "container-a"
CONTAINER_B = "container-b"

# Keyed by entra_principals[].key in variables.auto.tfvars.json. env_prefix
# names the ENTRA_<PREFIX>_{CLIENT_ID,CLIENT_SECRET,KEY_FILE} variables
# env-entra.sh exports.
PRINCIPALS = {
    "reader_a": {"env_prefix": "ENTRA_READER_A", "container": CONTAINER_A},
    "writer_b": {"env_prefix": "ENTRA_WRITER_B", "container": CONTAINER_B},
}


def sftp_path(container, rel=""):
    """Absolute SFTP path for a container-relative path."""
    return f"/{container}/{rel}" if rel else f"/{container}"


def rid():
    return uuid.uuid4().hex[:8]


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


# ── Assertions ──────────────────────────────────────────────────────────────

def assert_sftp_denied(fn):
    """The operation must fail for lack of permission. A not-found error
    doesn't count: a wrong path would otherwise pass every deny test."""
    with pytest.raises(OSError) as exc_info:
        fn()
    assert not isinstance(exc_info.value, FileNotFoundError), (
        f"failed with not-found, not a permission denial: {exc_info.value}"
    )


# ── Entra certificate minting ───────────────────────────────────────────────

def ssh_keygen(*args):
    return subprocess.run(
        ["ssh-keygen", *args], check=True, capture_output=True, text=True,
    ).stdout


def cert_principal(cert_path):
    """The login name, read out of the certificate's Principals section rather
    than constructed: the docs don't settle whether it is the application
    (client) ID or the SP object ID. The certificate is authoritative."""
    lines = ssh_keygen("-L", "-f", cert_path).splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("Principals:"):
            for candidate in lines[i + 1:]:
                candidate = candidate.strip()
                if not candidate:
                    continue
                if candidate.endswith(":"):
                    break
                return candidate
    raise AssertionError(f"no Principals entry in certificate {cert_path}")


@dataclass
class EntraIdentity:
    name: str
    container: str
    key_path: str
    cert_path: str
    principal: str

    @property
    def username(self):
        return f"{STORAGE_ACCOUNT}.{self.principal}"


def _mint_identity(name, workdir):
    """Sign the SP in to Entra and have it sign its own public key.

    AZURE_CONFIG_DIR is redirected into a temp dir so this `az login` never
    touches (or logs out of) the operator's own az session.
    --allow-no-subscriptions is required: these SPs hold no RBAC anywhere.
    """
    p        = PRINCIPALS[name]
    prefix   = p["env_prefix"]
    key_path = os.environ[f"{prefix}_KEY_FILE"]
    cert_path = os.path.join(workdir, f"{name}-cert.pub")
    env = dict(os.environ, AZURE_CONFIG_DIR=os.path.join(workdir, "azure"))

    subprocess.run(
        ["az", "login", "--service-principal",
         "-u", os.environ[f"{prefix}_CLIENT_ID"],
         "-p", os.environ[f"{prefix}_CLIENT_SECRET"],
         "--tenant", TENANT_ID, "--allow-no-subscriptions"],
        env=env, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["az", "sftp", "cert", "--public-key-file", f"{key_path}.pub", "--file", cert_path],
        env=env, check=True, capture_output=True, text=True,
    )
    return EntraIdentity(name, p["container"], key_path, cert_path, cert_principal(cert_path))


@pytest.fixture(scope="session")
def identities():
    """Both principals' key + freshly minted certificate, minted once."""
    with tempfile.TemporaryDirectory() as workdir:
        yield {name: _mint_identity(name, workdir) for name in PRINCIPALS}


def sftp_connect(username, key_path, cert_path=None):
    """Open an SFTP session. With cert_path=None the bare key is offered,
    which Entra SFTP should refuse -- nothing is registered for it."""
    key = paramiko.RSAKey.from_private_key_file(key_path)
    if cert_path:
        # Sets key.public_blob, which is what makes paramiko offer the
        # rsa-sha2-*-cert-v01@openssh.com algorithms Azure requires.
        key.load_certificate(cert_path)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=SFTP_HOST, port=22, username=username, pkey=key,
            look_for_keys=False, allow_agent=False,
        )
        return ssh.open_sftp(), ssh
    except Exception:
        ssh.close()
        raise


def _session(identity):
    sftp, ssh = sftp_connect(identity.username, identity.key_path, identity.cert_path)
    try:
        yield sftp
    finally:
        sftp.close()
        ssh.close()


@pytest.fixture(scope="session")
def reader_a(identities):
    """reader_a's session. Absolute paths only -- never chdir on it."""
    yield from _session(identities["reader_a"])


@pytest.fixture(scope="session")
def writer_b(identities):
    """writer_b's session. Absolute paths only -- never chdir on it."""
    yield from _session(identities["writer_b"])


@pytest.fixture
def fresh_sftp(identities):
    """Factory for a brand-new connection, for tests that chdir or use
    relative paths. Closed after the test, so its cwd can't leak."""
    opened = []

    def _open(name):
        i = identities[name]
        sftp, ssh = sftp_connect(i.username, i.key_path, i.cert_path)
        opened.append((sftp, ssh))
        return sftp

    yield _open
    for sftp, ssh in opened:
        sftp.close()
        ssh.close()


# ── Admin (Terraform SP, Storage Blob Data Owner = ACL superuser) ───────────

def _client(client_id, client_secret):
    cred = ClientSecretCredential(
        tenant_id=TENANT_ID, client_id=client_id, client_secret=client_secret,
    )
    return DataLakeServiceClient(account_url=ACCOUNT_URL, credential=cred)


@pytest.fixture(scope="session")
def admin_client():
    """Seeds fixtures, verifies what the write-only principal can't read back,
    and cleans up (azurerm_role_assignment.tf_executor_blob_owner)."""
    return _client(os.environ["ARM_CLIENT_ID"], os.environ["ARM_CLIENT_SECRET"])


@dataclass
class Seed:
    container: str
    file: str        # container-relative
    nested_dir: str  # container-relative
    nested_file: str # container-relative
    content: bytes


@pytest.fixture(scope="session")
def seeds(admin_client):
    """Admin puts a file and a nested dir/file into each container, so every
    read test reads something real and every deny test targets a path that
    demonstrably exists. Removed at session end.
    """
    run = rid()
    out = {}
    for container in (CONTAINER_A, CONTAINER_B):
        fs = admin_client.get_file_system_client(container)
        s = Seed(
            container=container,
            file=f"seed-{run}.txt",
            nested_dir=f"seed-{run}",
            nested_file=f"seed-{run}/nested.txt",
            content=f"seed for {container}\n".encode(),
        )
        fs.get_directory_client(s.nested_dir).create_directory()
        _log_created(container, "dir", s.nested_dir)
        for rel in (s.file, s.nested_file):
            fs.get_file_client(rel).upload_data(s.content, overwrite=True)
            _log_created(container, "file", rel)
        out[container] = s
    yield out
    for s in out.values():
        fs = admin_client.get_file_system_client(s.container)
        for kind, rel in (("file", s.nested_file), ("file", s.file), ("dir", s.nested_dir)):
            try:
                if kind == "file":
                    fs.get_file_client(rel).delete_file()
                else:
                    fs.get_directory_client(rel).delete_directory()
            except ResourceNotFoundError:
                pass
            _log_deleted(s.container, kind, rel)


# ── Artifact cleanup ────────────────────────────────────────────────────────

class _TrackedCreations(list):
    """Logs every appended (kind, path, container) to CREATED_LOG as it's
    added, so the sweep can find it even if the run is killed."""

    def append(self, item):
        kind, path, container = item
        _log_created(container, kind, path)
        super().append(item)


@pytest.fixture
def container_cleanup(admin_client):
    """Per-test cleanup of exactly the artifacts a test creates: a test appends
    ("file"|"dir", container_relative_path, container) for each, and the admin
    removes them in reverse order (children before parents)."""
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
    """Safety net for a crashed run: deletes exactly what this harness logged
    as created and never deleted -- never anything pre-existing. Deepest
    first. Run via sweep_artifacts.py once no pytest session is using the
    account."""
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


def pytest_collection_modifyitems(items):
    order = ["test_entra_identity", "test_entra_reader_a", "test_entra_writer_b"]

    def sort_key(item):
        for i, name in enumerate(order):
            if name in item.nodeid:
                return i
        return len(order)
    items.sort(key=sort_key)
