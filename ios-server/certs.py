"""Certificates for the iPhone setup: a private root CA, the server certificate, and an iOS profile.

The root is limited with name constraints to gumi.sg and exvius.com, so even though the phone
trusts it, it cannot vouch for any other site. The root lasts ten years; the server certificate
lasts 397 days and is renewed from the same root, so the phone's profile never needs reinstalling
unless the certs folder is deleted.
"""
from __future__ import annotations

import datetime
import plistlib
import uuid
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT_NAME = 'Exvius Offline Root'
LEAF_HOST = 'v900-lapis.gumi.sg'
LEAF_SANS = ('v900-lapis.gumi.sg', '*.gumi.sg', 'gumi.sg', '*.exvius.com', '*.notice.exvius.com')
PERMITTED = ('gumi.sg', 'exvius.com')
ROOT_DAYS = 3650
LEAF_DAYS = 397
RENEW_BEFORE = datetime.timedelta(days=30)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _write(path: Path, data: bytes, mode: int = 0o644) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(data)
    tmp.chmod(mode)
    tmp.replace(path)


def _make_root(folder: Path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Exvius Offline'),
                      x509.NameAttribute(NameOID.COMMON_NAME, ROOT_NAME)])
    now = _now()
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=ROOT_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         key_cert_sign=True, crl_sign=True, encipher_only=False,
                                         decipher_only=False), critical=True)
            .add_extension(x509.NameConstraints(
                permitted_subtrees=[x509.DNSName(d) for d in PERMITTED], excluded_subtrees=None), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    _write(folder / 'ca.key', key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                serialization.NoEncryption()), 0o600)
    _write(folder / 'ca.pem', cert.public_bytes(serialization.Encoding.PEM))
    _write(folder / 'ca.crt', cert.public_bytes(serialization.Encoding.DER))
    (folder / 'leaf.pem').unlink(missing_ok=True)  # a new root needs a new leaf
    return key, cert


def _make_leaf(folder: Path, ca_key, ca_cert) -> x509.Certificate:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = _now()
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Exvius Offline'),
                                     x509.NameAttribute(NameOID.COMMON_NAME, LEAF_HOST)]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=LEAF_DAYS))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in LEAF_SANS]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _write(folder / 'leaf.key', key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()), 0o600)
    leaf_pem = cert.public_bytes(serialization.Encoding.PEM)
    _write(folder / 'leaf.pem', leaf_pem)
    _write(folder / 'leaf-chain.pem', leaf_pem + ca_cert.public_bytes(serialization.Encoding.PEM))
    return cert


def _profile(folder: Path, ca_cert: x509.Certificate) -> None:
    """An iOS configuration profile holding the root certificate (Settings installs it)."""
    marker = folder / 'profile-ids.txt'
    if marker.exists():
        outer, inner = marker.read_text().split()
    else:
        outer, inner = str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper()
        marker.write_text(outer + ' ' + inner)
    profile = {
        'PayloadContent': [{
            'PayloadCertificateFileName': 'exvius-offline-root.cer',
            'PayloadContent': ca_cert.public_bytes(serialization.Encoding.DER),
            'PayloadDescription': 'Lets Final Fantasy Brave Exvius talk to your Exvius Offline server.',
            'PayloadDisplayName': ROOT_NAME,
            'PayloadIdentifier': 'com.exvius.offline.root.' + inner,
            'PayloadType': 'com.apple.security.root',
            'PayloadUUID': inner,
            'PayloadVersion': 1,
        }],
        'PayloadDescription': 'Root certificate for the Exvius Offline game server. It can only vouch for '
                              'gumi.sg and exvius.com addresses.',
        'PayloadDisplayName': 'Exvius Offline server',
        'PayloadIdentifier': 'com.exvius.offline.' + outer,
        'PayloadRemovalDisallowed': False,
        'PayloadType': 'Configuration',
        'PayloadUUID': outer,
        'PayloadVersion': 1,
    }
    _write(folder / 'exvius-offline.mobileconfig', plistlib.dumps(profile))


def ensure(folder: Path) -> dict:
    """Create whatever is missing or expiring; return the paths the server needs."""
    folder.mkdir(parents=True, exist_ok=True)
    ca_key = ca_cert = None
    if (folder / 'ca.key').exists() and (folder / 'ca.pem').exists():
        ca_key = serialization.load_pem_private_key((folder / 'ca.key').read_bytes(), None)
        ca_cert = x509.load_pem_x509_certificate((folder / 'ca.pem').read_bytes())
        if ca_cert.not_valid_after_utc - _now() < RENEW_BEFORE:
            ca_key = ca_cert = None
            print('[ios-server] root certificate expiring: making a new one (reinstall the phone profile)',
                  flush=True)
    if ca_cert is None:
        ca_key, ca_cert = _make_root(folder)
        print('[ios-server] created a new root certificate', flush=True)
    leaf = None
    if (folder / 'leaf.pem').exists() and (folder / 'leaf.key').exists() and (folder / 'leaf-chain.pem').exists():
        leaf = x509.load_pem_x509_certificate((folder / 'leaf.pem').read_bytes())
        if leaf.issuer != ca_cert.subject or leaf.not_valid_after_utc - _now() < RENEW_BEFORE:
            leaf = None
    if leaf is None:
        leaf = _make_leaf(folder, ca_key, ca_cert)
        print('[ios-server] issued a new server certificate', flush=True)
    if not (folder / 'ca.crt').exists():
        _write(folder / 'ca.crt', ca_cert.public_bytes(serialization.Encoding.DER))
    _profile(folder, ca_cert)
    return {'leaf_chain': folder / 'leaf-chain.pem', 'leaf_key': folder / 'leaf.key',
            'profile': folder / 'exvius-offline.mobileconfig', 'ca_der': folder / 'ca.crt',
            'leaf_expires': leaf.not_valid_after_utc}
