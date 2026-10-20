"""Each principal authenticates with its own key pair, and only as itself.

Entra SFTP registers nothing on the storage account: a principal proves who
it is by presenting an OpenSSH certificate that Entra signed over its public
key while signed in as that principal. These tests pin down that each SP's
certificate is bound to *its own* key pair and *its own* identity, so the
access tests in the other modules can't pass because of a crossed wire.
"""
import re

import paramiko
import pytest

from conftest import PRINCIPALS, sftp_connect, ssh_keygen


def _fingerprint_of_key(pub_path):
    return ssh_keygen("-l", "-f", pub_path).split()[1]


def _fingerprint_of_cert(cert_path):
    m = re.search(r"Public key: \S+ (SHA256:\S+)", ssh_keygen("-L", "-f", cert_path))
    assert m, f"no public key line in certificate {cert_path}"
    return m.group(1)


@pytest.mark.parametrize("name", list(PRINCIPALS))
def test_cert_is_over_principals_own_key(identities, name):
    i = identities[name]
    assert _fingerprint_of_cert(i.cert_path) == _fingerprint_of_key(f"{i.key_path}.pub")


def test_principals_have_distinct_keys(identities):
    a, b = identities["reader_a"], identities["writer_b"]
    assert _fingerprint_of_key(f"{a.key_path}.pub") != _fingerprint_of_key(f"{b.key_path}.pub")


def test_principals_have_distinct_identities(identities):
    assert identities["reader_a"].principal != identities["writer_b"].principal


@pytest.mark.parametrize("name", list(PRINCIPALS))
def test_connects_with_own_key_and_cert(identities, name):
    i = identities[name]
    sftp, ssh = sftp_connect(i.username, i.key_path, i.cert_path)
    try:
        assert ssh.get_transport().is_authenticated()
    finally:
        sftp.close()
        ssh.close()


@pytest.mark.parametrize("name,other", [("reader_a", "writer_b"), ("writer_b", "reader_a")])
def test_cannot_log_in_as_other_principal(identities, name, other):
    """Own key + cert, other principal's username: the certificate doesn't
    list that principal, so authentication must fail."""
    i = identities[name]
    with pytest.raises(paramiko.AuthenticationException):
        sftp_connect(identities[other].username, i.key_path, i.cert_path)


@pytest.mark.parametrize("name", list(PRINCIPALS))
def test_bare_key_without_cert_is_refused(identities, name):
    """The key pair alone is not a credential -- only Entra's signature is."""
    i = identities[name]
    with pytest.raises(paramiko.AuthenticationException):
        sftp_connect(i.username, i.key_path)
