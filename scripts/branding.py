#!/usr/bin/env python3
"""Apply brand/brand.json to a patched Chromium source tree.

    branding.py <chromium src dir>

What it changes:
  * chrome/app/theme/chromium/BRANDING  (product/company names, copyright)
  * chrome/install_static/chromium_install_modes.h  (install + user data
    paths, ProgIDs, URL scheme, Active Setup GUID)
  * user-visible "Chromium" strings, *with* their translations;
  * product icons, rendered from brand/logo.svg.

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


def _guid_initializer(guid):
    """{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX} -> C++ GUID initializer."""
    h = guid.strip('{}').replace('-', '')
    tail = ', '.join(f'0x{h[i:i + 2]}' for i in range(16, 32, 2))
    return f'{{0x{h[0:8]}, 0x{h[8:12]}, 0x{h[12:16]}, {{{tail}}}}}'


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
    for field, guid in i['clsids'].items():
        if field.startswith('_'):
            continue
        text = re.sub(rf'\.{field} = \{{0x[0-9A-Fa-f]+,\s*0x[0-9A-Fa-f]+,\s*0x[0-9A-Fa-f]+,\s*\{{[^}}]*\}}\}}',
                      f'.{field} = {_guid_initializer(guid)}', text)
        if _guid_initializer(guid) not in text:
            raise SystemExit(f'install modes: could not set {field}')
    for old, new in replacements:
        if new in text:  # already applied
            continue
        if old not in text:
            raise SystemExit(f'install modes: anchor not found: {old}')
        text = text.replace(old, new)
    write(p, text)


def _png(svg, size, out):
    import cairosvg
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + '.hb-tmp')
    cairosvg.svg2png(url=str(svg), write_to=str(tmp), output_width=size, output_height=size)
    tmp.replace(out)


def _wordmark(svg, height, color, out):
    """Logo + "Hivey" in Space Grotesk Bold, at the size Chromium expects."""
    import io
    import cairosvg
    from PIL import Image, ImageDraw, ImageFont
    scale = height // 22
    width = 97 * scale
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    icon = Image.open(io.BytesIO(cairosvg.svg2png(url=str(svg), output_width=height, output_height=height)))
    canvas.paste(icon, (0, 0), icon)
    font = ImageFont.truetype(str(ROOT / 'brand' / 'fonts' / 'SpaceGrotesk.ttf'), int(15 * scale))
    font.set_variation_by_name('Bold')
    draw = ImageDraw.Draw(canvas)
    box = draw.textbbox((0, 0), BRAND['short_name'], font=font)
    draw.text((height + 4 * scale, (height - (box[3] - box[1])) // 2 - box[1]), BRAND['short_name'],
              font=font, fill=color)
    canvas.save(out.with_name(out.name + '.hb-tmp'), format='PNG')
    out.with_name(out.name + '.hb-tmp').replace(out)


def rebrand_icons(src):
    """Every Chromium product logo replaced by brand/logo.svg renders."""
    from PIL import Image
    svg = ROOT / 'brand' / 'logo.svg'
    theme = src / 'chrome/app/theme'
    for size in (16, 24, 32, 48, 64, 128, 256):
        if (theme / f'chromium/product_logo_{size}.png').exists():
            _png(svg, size, theme / f'chromium/product_logo_{size}.png')
    for scale, folder in ((1, 'default_100_percent'), (2, 'default_200_percent')):
        for size in (16, 32):
            _png(svg, size * scale, theme / folder / 'chromium' / f'product_logo_{size}.png')
        _wordmark(svg, 22 * scale, (32, 24, 12, 255), theme / folder / 'chromium' / 'product_logo_name_22.png')
        _wordmark(svg, 22 * scale, (255, 255, 255, 255),
                  theme / folder / 'chromium' / 'product_logo_name_22_white.png')
    _png(svg, 600, theme / 'chromium/win/tiles/Logo.png')
    _png(svg, 176, theme / 'chromium/win/tiles/SmallLogo.png')
    # Multi-size .ico for the executable, the app list and the installer.
    big = theme / 'chromium/win/hivey-256.png.hb-tmp'
    _png(svg, 256, big)
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    for name in ('chromium.ico', 'app_list.ico'):
        out = theme / 'chromium/win' / name
        Image.open(big).save(out.with_name(name + '.hb-tmp'), format='ICO', sizes=ico_sizes)
        out.with_name(name + '.hb-tmp').replace(out)
    big.unlink()
    print('[brand] icons rendered from brand/logo.svg')


def main():
    src = Path(sys.argv[1]).resolve()
    rebrand_branding_file(src)
    rebrand_install_modes(src)
    rebrand_icons(src)
    rebrand_strings(src, BRAND['product_name'])
    print(f"[brand] applied: {BRAND['product_name']}")


if __name__ == '__main__':
    main()
