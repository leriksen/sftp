import io
import os
import uuid
import paramiko
import pytest
from azure.core.exceptions import HttpResponseError
from azure.identity import ClientSecretCredential
from azure.storage.filedatalake import DataLakeServiceClient

TENANT_ID       = os.environ["AZURE_TENANT_ID"]
STORAGE_ACCOUNT = os.environ.get("SFTP_STORAGE_ACCOUNT", "stsftpdemo0721")
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


@pytest.fixture
def container_cleanup(admin_client):
    """Per-test cleanup of exactly the artifacts a test creates.

    A test appends ("file"|"dir", container_relative_path, container) for
    each artifact it creates. After the test the admin removes exactly
    those, in reverse creation order (children before parents).
    """
    created = []
    yield created
    for kind, path, container in reversed(created):
        fs = admin_client.get_file_system_client(container)
        if kind == "file":
            fs.get_file_client(path).delete_file()
        else:
            fs.get_directory_client(path).delete_directory()


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
    sftp_inbound_client.putfo(io.BytesIO(b"hello from inbound"), seed, confirm=False)

    yield {"scratch_dir": scratch, "seed_file": seed}

    fs = admin_client.get_file_system_client(INBOUND_CONTAINER)
    fs.get_file_client(f"{HOME_DIR}/{seed}").delete_file()
    fs.get_directory_client(f"{HOME_DIR}/{scratch}").delete_directory()


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
