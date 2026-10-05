#!/usr/bin/env python3
"""Apply brand/brand.json to a patched Chromium source tree.

    branding.py <chromium src dir>

What it changes:
  * chrome/app/theme/chromium/BRANDING  (product/company names, copyright)
  * chrome/install_static/chromium_install_modes.h  (install + user data
    paths, ProgIDs, URL scheme, Active Setup GUID)
  * user-visible "Chromium" strings, *with* their translations.

Why the strings need care: every translation in a .xtb file is keyed by a
fingerprint of the English source text. Replacing "Chromium" in the .grd
alone would change every fingerprint and silently drop all translations (the
browser would fall back to English with no error). So we parse each .grd with
Chromium's own grit before and after the rename, and re-key the .xtb files
from old fingerprint to new one.

"The Chromium Authors" is kept verbatim: crediting them is required by
Chromium's BSD license.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = json.loads((ROOT / 'brand' / 'brand.json').read_text())

# (grd, extra files substituted with it, i.e. its <part> files)
STRING_FILES = [
    ('chrome/app/chromium_strings.grd', ['chrome/app/settings_chromium_strings.grdp']),
    ('components/components_chromium_strings.grd', []),
]

KEEP = 'The Chromium Authors'
SENTINEL = '\x00KEEP\x00'


def write(path, text):
    """Replace the file instead of rewriting it in place (keeps hardlinked
    copies of the tree untouched)."""
    tmp = path.with_name(path.name + '.hb-tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def rename(text, name):
    text = text.replace(KEEP, SENTINEL)
    text = re.sub(r'\bChromium\b', name, text)
    return text.replace(SENTINEL, KEEP)


def message_ids(src, grd):
    """[(message name, fingerprint)] in document order, for every message."""
    sys.path.insert(0, str(src / 'tools' / 'grit'))
    from grit import grd_reader
    from grit.node import message
    # Messages stay in the tree whatever the <if> conditions evaluate to, so
    # any build variable we do not know can safely read as False.
    class Defines(dict):
        def __contains__(self, key):
            return True

        def __missing__(self, key):
            return False
    defines = Defines(_chromium=True)
    root = grd_reader.Parse(str(src / grd), debug=False, defines=defines, target_platform='win32')
    out = []
    for node in root.GetChildrenOfType(message.MessageNode):
        out.append((node.attrs['name'], node.GetCliques()[0].GetMessage().GetId()))
    return out


def rebrand_strings(src, name):
    total_rekeyed = 0
    for grd, parts in STRING_FILES:
        before = message_ids(src, grd)
        for rel in [grd] + parts:
            p = src / rel
            write(p, rename(p.read_text(encoding='utf-8'), name))
        after = message_ids(src, grd)
        if [n for n, _ in before] != [n for n, _ in after]:
            raise SystemExit(f'{grd}: message list changed while renaming')
        remap = {old: new for (_, old), (_, new) in zip(before, after) if old != new}

        grd_text = (src / grd).read_text(encoding='utf-8')
        xtbs = re.findall(r'<file path="([^"]+\.xtb)"', grd_text)
        for xtb in xtbs:
            p = (src / grd).parent / xtb
            text = p.read_text(encoding='utf-8')

            def rekey(m):
                return f'<translation id="{remap.get(m.group(1), m.group(1))}"'
            text = re.sub(r'<translation id="(\d+)"', rekey, text)
            write(p, rename(text, name))
        total_rekeyed += len(remap)
        print(f'[brand] {grd}: {len(remap)} messages re-keyed across {len(xtbs)} translations')
    return total_rekeyed


def rebrand_branding_file(src):
    p = src / 'chrome/app/theme/chromium/BRANDING'
    values = {
        'COMPANY_FULLNAME': BRAND['company_name'],
        'COMPANY_SHORTNAME': BRAND['company_name'],
        'PRODUCT_FULLNAME': BRAND['product_name'],
        'PRODUCT_SHORTNAME': BRAND['short_name'],
        'PRODUCT_INSTALLER_FULLNAME': f"{BRAND['product_name']} Installer",
        'PRODUCT_INSTALLER_SHORTNAME': f"{BRAND['short_name']} Installer",
        'COPYRIGHT': f"Copyright @LASTCHANGE_YEAR@ {BRAND['copyright_holder']} and The Chromium Authors. "
                     'All rights reserved.',
    }
    lines = []
    for line in p.read_text().splitlines():
        key = line.split('=', 1)[0]
        lines.append(f'{key}={values[key]}' if key in values else line)
    write(p, '\n'.join(lines) + '\n')


def rebrand_install_modes(src):
    p = src / 'chrome/install_static/chromium_install_modes.h'
    i = BRAND['install']
    name = BRAND['product_name']
    text = p.read_text()
    replacements = [
        ('kCompanyPathName[] = L"";', f'kCompanyPathName[] = L"{i["company_path"]}";'),
        ('kProductPathName[] = L"Chromium";', f'kProductPathName[] = L"{i["product_path"]}";'),
        ('.base_app_name = L"Chromium",', f'.base_app_name = L"{name}",'),
        ('.base_app_id = L"Chromium",', f'.base_app_id = L"{i["base_app_id"]}",'),
        ('.browser_prog_id_prefix = L"ChromiumHTM",', f'.browser_prog_id_prefix = L"{i["prog_id_prefix"]}",'),
        ('L"Chromium HTML Document",', f'L"{name} HTML Document",'),
        ('.direct_launch_url_scheme = "chromium",', f'.direct_launch_url_scheme = "{i["url_scheme"]}",'),
        ('.pdf_prog_id_prefix = L"ChromiumPDF",', f'.pdf_prog_id_prefix = L"{i["pdf_prog_id_prefix"]}",'),
        ('L"Chromium PDF Document",', f'L"{name} PDF Document",'),
        ('L"{7D2B3E1D-D096-4594-9D8F-A6667F12E0AC}",', f'L"{i["active_setup_guid"]}",'),
    ]
    for old, new in replacements:
        if new in text:  # already applied
            continue
        if old not in text:
            raise SystemExit(f'install modes: anchor not found: {old}')
        text = text.replace(old, new)
    write(p, text)


def main():
    src = Path(sys.argv[1]).resolve()
    rebrand_branding_file(src)
    rebrand_install_modes(src)
    rebrand_strings(src, BRAND['product_name'])
    print(f"[brand] applied: {BRAND['product_name']}")


if __name__ == '__main__':
    main()
