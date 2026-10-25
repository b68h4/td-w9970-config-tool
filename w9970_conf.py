#!/usr/bin/env python3
"""Decrypt / re-encrypt TP-Link TD-W9970 v3 router backup config files.

  conf.bin  (encrypted)  <->  conf.xml  (plain, editable)

The tool auto-detects the direction from the input:
  * a file starting with "<?xml" is compressed + encrypted into a .bin
  * anything else is treated as a .bin and decrypted into XML

Encryption scheme (verified by an exact byte-for-byte round-trip against a
real TD-W9970 v3 backup):

    DES-ECB, big-endian size field, body = MD5(compressed) + compressed,
    zero-padded to a multiple of 8 bytes. LZSS compression is provided by
    the referenced `tp.py` (see referenced_scripts/).

The DES key is NOT fixed: TP-Link derives it from the device Product ID as

    key = BASE_KEY XOR ascii(product_id)

where BASE_KEY = 74 8d a5 0b f9 3e 2d cf and product_id is formatted as 8
lowercase hex characters. For the Turk Telekom (TTNET) TD-W9970 v3 the
Product ID is 0x08860001, which yields key 44 b5 9d 3d c9 0e 1d fe.
"""

import argparse
import os
import struct
import sys
from hashlib import md5

# The LZSS compress/uncompress routines live in the referenced upstream script.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "referenced_scripts"))
import tp  # noqa: E402  (path is set up above)

try:
    from Cryptodome.Cipher import DES   # pycryptodomex
except ImportError:                      # pragma: no cover
    from Crypto.Cipher import DES        # pycryptodome

# Base key extracted from the TP-Link firmware; XORed with the Product ID.
BASE_KEY = bytes.fromhex("748da50bf93e2dcf")

# Default Product ID for the Turk Telekom (TTNET) TD-W9970 v3.
DEFAULT_PRODUCT_ID = 0x08860001


def derive_key(product_id: int) -> bytes:
    """Return the 8-byte DES key for a given Product ID."""
    pid_hex = f"{product_id:08x}".encode("ascii")
    return bytes(b ^ p for b, p in zip(BASE_KEY, pid_hex))


def decrypt(data: bytes, key: bytes) -> bytes:
    """Decrypt a conf.bin buffer and return the plain XML."""
    if len(data) % 8:
        raise ValueError("Encrypted file length must be a multiple of 8 bytes.")

    decrypted = DES.new(key, DES.MODE_ECB).decrypt(data)

    # The first 16 bytes are the MD5 digest of the (zero-trimmed) body.
    for pad in range(8):
        body = decrypted[16:len(decrypted) - pad]
        if body and md5(body).digest() == decrypted[:16]:
            break
    else:
        raise ValueError(
            "MD5 check failed - wrong key or not a TD-W9970 v3 backup file.")

    # The body is a big-endian size header followed by LZSS-compressed XML.
    tp.packint = ">I"
    return bytes(tp.uncompress(body))


def encrypt(xml: bytes, key: bytes) -> bytes:
    """Compress + encrypt plain XML back into a conf.bin buffer."""
    tp.packint = ">I"
    size, dst = tp.compress(xml, False)
    dst = bytes(dst[:size])

    body = md5(dst).digest() + dst
    if len(body) % 8:                      # DES needs a multiple of 8 bytes
        body += b"\0" * (8 - (len(body) % 8))

    return DES.new(key, DES.MODE_ECB).encrypt(body)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decrypt / re-encrypt TP-Link TD-W9970 v3 config backups.")
    parser.add_argument("input", help="conf.bin (to decrypt) or conf.xml (to encrypt)")
    parser.add_argument("output", help="output file path")
    parser.add_argument("-p", "--product-id", default=hex(DEFAULT_PRODUCT_ID),
                        help="device Product ID, e.g. 0x08860001 (default: TTNET W9970v3)")
    parser.add_argument("-k", "--key",
                        help="raw 8-byte DES key as hex (overrides --product-id)")
    parser.add_argument("-f", "--force", action="store_true",
                        help="overwrite the output file if it already exists")
    args = parser.parse_args()

    if args.key:
        key = bytes.fromhex(args.key)
        if len(key) != 8:
            parser.error("--key must be exactly 8 bytes (16 hex characters).")
    else:
        key = derive_key(int(args.product_id, 0))

    if os.path.exists(args.output) and not args.force:
        parser.error(f"output file exists: {args.output} (use -f to overwrite)")

    data = open(args.input, "rb").read()
    if data[:5] == b"<?xml":
        result = encrypt(data, key)
        action = "Encrypted"
    else:
        result = decrypt(data, key)
        action = "Decrypted"

    with open(args.output, "wb") as f:
        f.write(result)
    print(f"{action}: {args.input} -> {args.output} ({len(result)} bytes), "
          f"key={key.hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
