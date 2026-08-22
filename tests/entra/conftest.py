"""Fixtures for the Entra ID SFTP experiment (storage account "02").

Differs from the local-user suite in tests/ in three structural ways:

1. No local users exist on this account. Principals are Entra service
   principals, each a member of exactly one group created by entra.tf, and
   authorization is decided purely by named group ACEs -- neither SP holds any
   data-plane RBAC (see the comment on azurerm_role_assignment.aad_reader in
   sa.tf for why granting one would invalidate the whole experiment).

2. Authentication is an OpenSSH certificate rather than a bare key. The SP
   signs in to Entra, exchanges its token for a certificate via `az sftp cert`,
   and paramiko presents key + certificate. Certificates are valid for 65
   minutes, so they are minted once per session.

3. There is no home directory -- Microsoft explicitly does not support setting
   one for Entra principals. Every connection lands at the account root and
   must `cd` into a container, so all paths here are container-qualified
   ("sftp/inbound/dev01/..."), unlike the local-user suite's home-relative
   paths.

4. Both principals share ONE container. Account "01" needs two (inbound and
   outbound) because an SFTP local user is authorized through `other::`, which
   every local user in a container shares -- so isolation there can only be
   drawn at a container boundary, one user per container. Named group ACEs are
   per-principal, so account "02" draws the same boundary at a *subtree*
   inside a single container. That is the claim this suite exists to test, and
   the reason the deny cases below assert cross-tree rather than
   cross-container isolation.

The artifact ledger is deliberately separate from tests/.artifacts_*.jsonl:
that one is swept by tests/sweep_artifacts.py, whose admin client is bound to
account "01" and so cannot delete anything created here.
"""
import json
import os
import subprocess
import tempfile

import paramiko
import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import ClientSecretCredential
from azure.storage.filedatalake import DataLakeServiceClient

TENANT_ID       = os.environ["AZURE_TENANT_ID"]
STORAGE_ACCOUNT = os.environ["ENTRA_STORAGE_ACCOUNT"]
ACCOUNT_URL     = f"https://{STORAGE_ACCOUNT}.dfs.core.windows.net"
SFTP_HOST       = f"{STORAGE_ACCOUNT}.blob.core.windows.net"

# One container holds both principals' trees. The writer and reader each get
# `--x` on this container root: traverse but not read, so neither can even
# enumerate the other subtree's *name*, let alone its contents.
SFTP_CONTAINER = "sftp"

WRITE_DIR = "inbound"   # writers' subtree; readers hold no ACE on it
READ_DIR  = "outbound"  # readers' subtree; writers hold no ACE on it
TREE_DIR  = "dev01"
NOTSFTP   = "notsftp"   # neither group holds an ACE anywhere on this

# Container-relative paths, for the DataLake clients (already container-scoped).
WRITE_TREE_REL = f"{WRITE_DIR}/{TREE_DIR}"
READ_TREE_REL  = f"{READ_DIR}/{TREE_DIR}"

# Container-qualified paths, for SFTP -- Entra SFTP has no home directory, so
# sessions land on the account root and every path starts with the container.
# Absolute (leading "/") deliberately: the SFTP clients are session-scoped, so
# one chdir in one test would otherwise re-root every relative path in every
# test after it -- and a deny assertion that fails for the wrong reason still
# looks green.
SFTP_ROOT  = f"/{SFTP_CONTAINER}"
WRITE_TREE = f"{SFTP_ROOT}/{WRITE_TREE_REL}"
READ_TREE  = f"{SFTP_ROOT}/{READ_TREE_REL}"

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

def assert_denied(fn):
    with pytest.raises(HttpResponseError) as exc_info:
        fn()
    assert exc_info.value.status_code == 403, (
        f"Expected 403, got {exc_info.value.status_code}"
    )


def assert_sftp_denied(fn):
    with pytest.raises(OSError):
        fn()


# ── Entra certificate minting ───────────────────────────────────────────────

def _cert_principal(cert_path):
    """Pull the login name out of the OpenSSH certificate's Principals section.

    Read rather than constructed: Microsoft's docs say to "use the service
    principal ID in place of the username" without settling whether that means
    the application (client) ID or the service principal's object ID. The
    certificate itself is authoritative.
    """
    out = subprocess.run(
        ["ssh-keygen", "-L", "-f", str(cert_path)],
        check=True, capture_output=True, text=True,
    ).stdout
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("Principals:"):
            for candidate in lines[i + 1:]:
                candidate = candidate.strip()
                if not candidate:
                    continue
                if candidate.endswith(":"):
                    break
                return candidate
    raise AssertionError(f"no Principals entry in certificate:\n{out}")


def _mint_certificate(client_id, client_secret, workdir):
    """Sign the SP in to Entra and exchange its token for an OpenSSH cert.

    AZURE_CONFIG_DIR is redirected into the per-fixture temp dir so this
    `az login` never touches (or logs out of) the operator's own az session.
    --allow-no-subscriptions is required: these SPs hold no RBAC anywhere, so
    the default login fails with "No subscriptions found" -- which is itself
    the point of the experiment.
    """
    env = dict(os.environ, AZURE_CONFIG_DIR=os.path.join(workdir, "azure"))
    key_path  = os.path.join(workdir, "id_rsa")
    cert_path = os.path.join(workdir, "id_rsa-cert.pub")

    # RSA only -- Entra does not issue ECDSA certificates.
    subprocess.run(
        ["ssh-keygen", "-t", "rsa", "-b", "2048", "-N", "", "-f", key_path, "-q"],
        check=True,
    )
    subprocess.run(
        ["az", "login", "--service-principal",
         "-u", client_id, "-p", client_secret,
         "--tenant", TENANT_ID, "--allow-no-subscriptions"],
        env=env, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["az", "sftp", "cert",
         "--public-key-file", f"{key_path}.pub",
         "--file", cert_path],
        env=env, check=True, capture_output=True, text=True,
    )
    return key_path, cert_path, _cert_principal(cert_path)


def _sftp_connect_entra(client_id, client_secret, workdir):
    key_path, cert_path, principal = _mint_certificate(client_id, client_secret, workdir)

    key = paramiko.RSAKey.from_private_key_file(key_path)
    # Sets key.public_blob, which is what makes paramiko offer the
    # rsa-sha2-*-cert-v01@openssh.com host-key algorithms Azure requires.
    key.load_certificate(cert_path)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname=SFTP_HOST,
        port=22,
        username=f"{STORAGE_ACCOUNT}.{principal}",
        pkey=key,
        look_for_keys=False,
        allow_agent=False,
    )
    return ssh.open_sftp(), ssh


def _entra_sftp_fixture(client_id_env, secret_env):
    with tempfile.TemporaryDirectory() as workdir:
        sftp, ssh = _sftp_connect_entra(
            os.environ[client_id_env],
            os.environ[secret_env],
            workdir,
        )
        try:
            yield sftp
        finally:
            sftp.close()
            ssh.close()


@pytest.fixture(scope="session")
def entra_writer_sftp():
    """SP in sftp-entra-writers. ACL: sftp/ --x, sftp/inbound/ --x,
    sftp/inbound/dev01 rwx access + -wx default -- the same shape sftpuser0
    gets from `other` on account 01, but scoped to a named group rather than
    to the whole container."""
    yield from _entra_sftp_fixture("ENTRA_WRITER_CLIENT_ID", "ENTRA_WRITER_CLIENT_SECRET")


@pytest.fixture(scope="session")
def entra_reader_sftp():
    """SP in sftp-entra-readers. ACL: sftp/ --x, sftp/outbound/ --x,
    sftp/outbound/dev01 r-x access + default -- the same shape sftpuser1 gets
    from `other` on account 01, but scoped to a named group rather than to the
    whole container."""
    yield from _entra_sftp_fixture("ENTRA_READER_CLIENT_ID", "ENTRA_READER_CLIENT_SECRET")


# ── Data-plane (REST) clients, for the ACL-parity control ───────────────────

def _client(client_id, client_secret):
    cred = ClientSecretCredential(
        tenant_id=TENANT_ID,
        client_id=client_id,
        client_secret=client_secret,
    )
    return DataLakeServiceClient(account_url=ACCOUNT_URL, credential=cred)


@pytest.fixture(scope="session")
def admin_client():
    """Terraform executor SP -- Storage Blob Data Owner on both accounts
    (azurerm_role_assignment.tf_executor_blob_owner in sa.tf), so it can verify
    and clean up artifacts the ACL-restricted principals can't read back."""
    return _client(os.environ["ARM_CLIENT_ID"], os.environ["ARM_CLIENT_SECRET"])


@pytest.fixture(scope="session")
def entra_writer_client():
    return _client(os.environ["ENTRA_WRITER_CLIENT_ID"], os.environ["ENTRA_WRITER_CLIENT_SECRET"])


@pytest.fixture(scope="session")
def entra_reader_client():
    return _client(os.environ["ENTRA_READER_CLIENT_ID"], os.environ["ENTRA_READER_CLIENT_SECRET"])


# ── Artifact cleanup ────────────────────────────────────────────────────────

class _TrackedCreations(list):
    def append(self, item):
        kind, path, container = item
        _log_created(container, kind, path)
        super().append(item)


@pytest.fixture
def container_cleanup(admin_client):
    """Per-test cleanup of exactly the artifacts a test creates: a test appends
    ("file"|"dir", container_relative_path, container) for each."""
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
            pass
        _log_deleted(container, kind, path)


def sweep_leftover_artifacts(admin_client):
    """Safety net for artifacts left behind by a crashed run. Deletes exactly
    what this harness logged as created and never deleted -- never anything
    pre-existing. Deepest-first, so a leftover child never blocks its parent."""
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
    def sort_key(item):
        if "test_entra_sftp_writer" in item.nodeid:
            return 0
        if "test_entra_sftp_reader" in item.nodeid:
            return 1
        if "test_entra_dataplane" in item.nodeid:
            return 2
        return 3
    items.sort(key=sort_key)
