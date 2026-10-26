#!/usr/bin/env python3
"""Pack a directory into a CRX3 extension package signed with an RSA key.

    crx3.py <extension dir> <key.pem> <out.crx>    (prints the extension ID)

CRX3 is what Chromium installs from a local file: "Cr24", format version 3,
a CrxFileHeader protobuf holding the key proof, then the zip. The extension
ID is derived from the public key, so the same key always gives the same ID.
Signing uses the openssl command line tool, so no Python package is needed.
The zip is deterministic (sorted entries, fixed timestamps).
"""

import hashlib
import io
import struct
import subprocess
import sys
import zipfile
from pathlib import Path


def _varint(n):
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(number, payload):
    """Length-delimited protobuf field (wire type 2)."""
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def ensure_key(key):
    """Create a 2048-bit RSA key (mode 0600) if it does not exist yet."""
    key = Path(key)
    if not key.exists():
        key.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                        '-out', str(key)], check=True, capture_output=True)
        key.chmod(0o600)
    return key


def public_key_der(key):
    return subprocess.run(['openssl', 'pkey', '-in', str(key), '-pubout', '-outform', 'DER'],
                          check=True, capture_output=True).stdout


def extension_id(public_key):
    """Chromium's ID: first 16 bytes of sha256(public key), hex digits a-p."""
    return ''.join(chr(ord('a') + int(c, 16)) for c in hashlib.sha256(public_key).hexdigest()[:32])


def deterministic_zip(directory):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(p for p in Path(directory).rglob('*') if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(directory).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return buf.getvalue()


def pack(directory, key, out):
    key = ensure_key(key)
    public_key = public_key_der(key)
    crx_id = hashlib.sha256(public_key).digest()[:16]
    signed_header_data = _field(1, crx_id)                       # SignedData.crx_id
    archive = deterministic_zip(directory)
    to_sign = b'CRX3 SignedData\x00' + struct.pack('<I', len(signed_header_data)) + signed_header_data + archive
    signature = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key)], input=to_sign,
                               check=True, capture_output=True).stdout
    proof = _field(1, public_key) + _field(2, signature)         # AsymmetricKeyProof
    header = _field(2, proof) + _field(10000, signed_header_data)  # CrxFileHeader
    Path(out).write_bytes(b'Cr24' + struct.pack('<II', 3, len(header)) + header + archive)
    return extension_id(public_key)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    print(pack(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
