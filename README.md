# TD-W9970 v3 Config Tool

Decrypt and re-encrypt TP-Link **TD-W9970 v3** router configuration backups
(`conf.bin` ⇄ `conf.xml`).

The stock TP-Link backup file is DES-encrypted, so you cannot read or edit it
directly. This tool recovers the plain XML, lets you edit it, and packs it back
into a valid `conf.bin` you can restore to the router.

> ⚠️ **Your `conf.xml` contains secrets** — PPPoE credentials, Wi-Fi keys, the
> device serial number and more. Never commit it or your `conf.bin` to a public
> repository. They are excluded via `.gitignore` in this project.

## Tested on

| | |
|---|---|
| Hardware | **TD-W9970 v3** (`TD-W9970 v3 00000002`) |
| Firmware | **23.08.17.01006** — Turk Telekom / TTNET branded |
| Product ID | `0x08860001` |
| DES key | `44b59d3dc90e1dfe` (DES-ECB) |

Other TD-W9970 variants (different ISPs/regions) use a **different Product ID**,
hence a different key. See [Other devices / keys](#other-devices--keys).

## Installation

Requires **Python 3.8+**. The only dependency is a DES implementation
(`pycryptodomex`).

```bash
# 1. Clone the repository
git clone https://github.com/b68h4/td-w9970-config-tool.git
cd td-w9970-config-tool

# 2. (optional) create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install the dependency
pip install -r requirements.txt
```

## Usage

```bash
# Decrypt: conf.bin -> conf.xml
python3 w9970_conf.py conf.bin conf.xml

# Edit conf.xml in any text editor, then ...

# Re-encrypt: conf.xml -> conf_new.bin  (restore this to the router)
python3 w9970_conf.py conf.xml conf_new.bin
```

### Worked example

```console
$ python3 w9970_conf.py conf.bin conf.xml
Decrypted: conf.bin -> conf.xml (41091 bytes), key=44b59d3dc90e1dfe

$ head -5 conf.xml
<?xml version="1.0"?>
<DslCpeConfig>
  <InternetGatewayDevice>
    <DeviceSummary val="InternetGatewayDevice:1.1[](Baseline:1, EthernetLAN:1)" />
    <LANDeviceNumberOfEntries val=1 />

# ... edit conf.xml as needed, then pack it back ...

$ python3 w9970_conf.py conf.xml conf_new.bin
Encrypted: conf.xml -> conf_new.bin (7272 bytes), key=44b59d3dc90e1dfe
```

`-h` shows all options, including `-f/--force` (overwrite output),
`-p/--product-id` and `-k/--key`.

The direction is auto-detected from the input (a file starting with `<?xml`
is encrypted, otherwise it is decrypted). Use `-f` to overwrite the output.

> **Note on the trailing byte.** The decrypted `conf.xml` ends with a single
> `0x00` (NUL) byte right after `</DslCpeConfig>` — this is part of the normal
> TP-Link format, not corruption (some editors render it as a stray space). You
> do not need to preserve it: if your editor strips the NUL or appends a newline,
> re-encryption still produces a valid file, because the packer re-adds the NUL
> terminator automatically.

### Other devices / keys

The key is derived from the device Product ID:

```
key = BASE_KEY XOR ascii(product_id)      # BASE_KEY = 74 8d a5 0b f9 3e 2d cf
```

If your TD-W9970 is a different variant, pass its Product ID (or the raw key):

```bash
python3 w9970_conf.py conf.bin conf.xml --product-id 0x08860001
python3 w9970_conf.py conf.bin conf.xml --key 44b59d3dc90e1dfe
```

## File layout

```
w9970_conf.py           # the tool (decrypt / encrypt)
requirements.txt
referenced_scripts/            # upstream references used for the LZSS codec
  ├── tpconf_bin_xml.py        # Alain Ducharme's tpconf_bin_xml (compress/uncompress)
  └── tp.rb                    # a Ruby DES reference for the same format
```

## How this was figured out

This project started from a `conf.bin` that no existing script could open. The
path to the key, step by step:

1. **Fingerprinting the file.** Entropy was ~7.97 bits/byte with no plaintext
   header and no repeating blocks → encrypted. The size was `7272 = 8 × 909`:
   a multiple of **8 but not 16**. That alone ruled out AES (16-byte blocks) and
   pointed at an **8-byte block cipher (DES)**.

2. **Separating two failures.** The reference scripts failed for two unrelated
   reasons. First, modern OpenSSL dropped DES and the machine had no crypto
   module, so the scripts died immediately — fixed by installing
   `pycryptodomex`. Second, with DES working, **none of the known keys matched**,
   so the real problem was a missing key.

3. **The key-derivation scheme.** TP-Link does not use one fixed key — it
   derives it as `BASE_KEY XOR ascii(product_id)`. Applying this to the known
   keys reproduced valid Product IDs, confirming the scheme and the base key
   `748da50bf93e2dcf`.

4. **Smart brute force.** The Product ID is 32-bit (~4.3 billion values). Rather
   than fully decrypting for each candidate, a **cheap one-block filter** was
   used: in the compressed format the first XML byte `<` (`0x3c`) lands at a
   fixed offset, so decrypting a single DES block rejects almost every wrong
   key instantly; only survivors got a full MD5 verification. Written in C and
   split across CPU cores, the whole 32-bit space scans in a few minutes.

   > A first attempt assumed a **little-endian** size field and found nothing;
   > this firmware uses a **big-endian** size. Switching to the `<`-byte filter
   > caught it.

5. **Recovering the key.** The scan returned many matches — all **DES
   parity-bit equivalents** of a single key (DES ignores the low bit of each key
   byte). The canonical key is `44b59d3dc90e1dfe`, from Product ID `0x08860001`.

6. **Decrypt → decompress → verify.** The decrypted payload was big-endian
   LZSS-compressed XML, unpacked with the referenced `tp.py`. Finally,
   re-encrypting the XML reproduced the **byte-for-byte identical** original
   `conf.bin`, proving the key, scheme and compression are all correct.

The TP-Link firmware image was only disassembled to *confirm* that the stock
2019 firmware uses the default key (`478da50bf9e3d2cf`) and not this one — the
actual key came from the brute force.

## Credits

- LZSS compress/uncompress and the overall `.bin`/`.xml` format:
  Alain Ducharme's [`tpconf_bin_xml`](https://github.com/sta-c0000/tpconf_bin_xml)
  (`referenced_scripts/tpconf_bin_xml.py`).

## License

Licensed under the **GNU General Public License v3.0** — see [`LICENSE`](LICENSE).

This is free software: you may use, modify and redistribute it, but any copy or
derivative **must stay under the GPLv3** and preserve attribution to the original
author. The project bundles and imports `tpconf_bin_xml.py` by Alain Ducharme,
which is itself GPLv3, so GPLv3 applies to the whole work.

## Disclaimer

For use only on devices you own. Restoring a modified configuration can
misconfigure or brick your router — keep an untouched backup of the original
`conf.bin`.
