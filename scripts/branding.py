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
import math
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
FIXED_TRANSLATIONS = {
    'IDS_ABOUT_VERSION_COMPANY_NAME': BRAND['company_name'],
    'IDS_ABOUT_VERSION_COPYRIGHT': f'Copyright <ph name="YEAR" /> {BRAND["copyright_holder"]} '
                                   'and The Chromium Authors. All rights reserved.',
}
SENTINEL = '\x00KEEP\x00'


def write(path, text):
    """Replace the file instead of rewriting it in place (keeps hardlinked
    copies of the tree untouched)."""
    tmp = path.with_name(path.name + '.hb-tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def credit_and_company(text):
    """The about pages and the installer's "Publisher" use the company name
    and copyright messages: the company becomes ours, the copyright credits
    both (BSD attribution of The Chromium Authors stays)."""
    company = BRAND['company_name']
    holder = BRAND['copyright_holder']
    # Company name message, in the .grd (multi-line) and in the .xtb files.
    text = re.sub(r'(name="IDS_ABOUT_VERSION_COMPANY_NAME"[^>]*>\s*)The Chromium Authors(\s*</message>)',
                  rf'\g<1>{company}\g<2>', text)
    text = text.replace('>The Chromium Authors</translation>', f'>{company}</translation>')
    # Copyright messages: "<year placeholder> The Chromium Authors".
    text = re.sub(rf'((?:</ph>|<ph name="YEAR"\s*/>)\s*)(?!{re.escape(holder)})The Chromium Authors',
                  rf'\g<1>{holder} and The Chromium Authors', text)
    return text


def rename(text, name):
    text = credit_and_company(text)
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
        # Translators localized "The Chromium Authors" ("Auteurs de Chromium"...),
        # so a rename would drop the credit in other languages: these messages
        # get the same fixed text in every language.
        fixed = {mid: FIXED_TRANSLATIONS[n] for n, mid in after if n in FIXED_TRANSLATIONS}

        grd_text = (src / grd).read_text(encoding='utf-8')
        xtbs = re.findall(r'<file path="([^"]+\.xtb)"', grd_text)
        for xtb in xtbs:
            p = (src / grd).parent / xtb
            text = p.read_text(encoding='utf-8')

            def rekey(m):
                return f'<translation id="{remap.get(m.group(1), m.group(1))}"'
            text = re.sub(r'<translation id="(\d+)"', rekey, text)
            text = rename(text, name)
            for mid, content in fixed.items():
                text = re.sub(rf'(<translation id="{mid}">).*?(</translation>)',
                              lambda m: m.group(1) + content + m.group(2), text)
            write(p, text)
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


LOGO = ROOT / 'brand' / 'logo.svg'
SVG_NS = 'http://www.w3.org/2000/svg'


def _mark_svg(size, fill=None):
    """brand/logo.svg with its bars snapped to the pixel grid of a `size` px image.

    The logo is four fully-rounded horizontal bars centered on the canvas. Drawn
    as is, their edges fall between pixels at small sizes (blurry at 16 px), so
    every bar gets a whole-pixel height, gap, top and width (width of the same
    parity as the image, so the bar stays centered). Height, gap and widths
    come from the rects of brand/logo.svg. Same rules as
    chrome/browser/hivey/hivey_app_icon.cc. `fill` replaces the gradient
    (monochrome icons).
    """
    import xml.etree.ElementTree as ET
    ET.register_namespace('', SVG_NS)
    tree = ET.parse(LOGO)
    svg = tree.getroot()
    view = float(svg.get('viewBox').split()[2])
    rects = svg.findall(f'.//{{{SVG_NS}}}rect')
    s = size / view
    height = float(rects[0].get('height'))
    gap = float(rects[1].get('y')) - float(rects[0].get('y')) - height
    h = max(3, int(height * s + 0.5))
    g = max(1, int(gap * s + 0.5))
    top = (size - (len(rects) * h + (len(rects) - 1) * g) + 1) // 2
    for i, rect in enumerate(rects):
        w = float(rect.get('width')) * s
        # Rounded half down, so bars of different widths stay different.
        w = 2 * math.ceil(w / 2 - 0.5) if size % 2 == 0 else 2 * math.ceil((w - 1) / 2 - 0.5) + 1
        w = min(w, size)
        y = top + i * (h + g)
        # Back to logo units, so the gradient keeps its coordinates.
        for key, value in (('x', (size - w) / 2), ('y', y), ('width', w), ('height', h), ('rx', h / 2)):
            rect.set(key, f'{value / s:.4f}')
        if fill:
            rect.set('fill', fill)
    return ET.tostring(svg)


def _render(size, fill=None):
    import io
    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(bytestring=_mark_svg(size, fill), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert('RGBA')


def _save(image, out, **kwargs):
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + '.hb-tmp')
    image.save(tmp, **kwargs)
    tmp.replace(out)


def _png(size, out, fill=None):
    _save(_render(size, fill), out, format='PNG')


def _ico(out, sizes=(16, 24, 32, 48, 64, 128, 256)):
    """Multi-size .ico, every size drawn at its own size (crisp at 16 px)."""
    images = [_render(size) for size in sizes]
    _save(images[-1], out, format='ICO', sizes=[(s, s) for s in sizes], append_images=images[:-1])


def _xpm(size, out):
    """XPM with 1-bit transparency (Linux menus that still want one)."""
    image = _render(size)
    opaque = [a >= 128 for a in image.getchannel('A').getdata()]
    indexed = image.convert('RGB').quantize(colors=64)
    palette = indexed.getpalette()
    chars = '.#$%&*+-/0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    pixels = list(indexed.getdata())
    used = sorted({p for p, o in zip(pixels, opaque) if o})
    lines = ['/* XPM */', 'static char *product_logo[] = {', f'"{size} {size} {len(used) + 1} 1",',
             '"  c None",']
    lines += ['"%s c #%02X%02X%02X",' % (chars[p], *palette[3 * p:3 * p + 3]) for p in used]
    rows = [''.join(chars[p] if o else ' ' for p, o in
                    zip(pixels[y * size:(y + 1) * size], opaque[y * size:(y + 1) * size]))
            for y in range(size)]
    lines += [f'"{row}",' for row in rows]
    lines[-1] = lines[-1][:-1]
    lines += ['};', '']
    tmp = out.with_name(out.name + '.hb-tmp')
    tmp.write_text('\n'.join(lines))
    tmp.replace(out)


def _wordmark(height, color, out):
    """Logo + "Hivey" in Space Grotesk Bold, at the size Chromium expects."""
    from PIL import Image, ImageDraw, ImageFont
    scale = height // 22
    width = 97 * scale
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    icon = _render(height)
    canvas.paste(icon, (0, 0), icon)
    font = ImageFont.truetype(str(ROOT / 'brand' / 'fonts' / 'SpaceGrotesk.ttf'), int(15 * scale))
    font.set_variation_by_name('Bold')
    draw = ImageDraw.Draw(canvas)
    box = draw.textbbox((0, 0), BRAND['short_name'], font=font)
    draw.text((height + 4 * scale, (height - (box[3] - box[1])) // 2 - box[1]), BRAND['short_name'],
              font=font, fill=color)
    _save(canvas, out, format='PNG')


def rebrand_icons(src):
    """Every Chromium product logo replaced by brand/logo.svg renders."""
    theme = src / 'chrome/app/theme'
    chromium = theme / 'chromium'
    for size in (16, 24, 32, 48, 64, 128, 256):
        if (chromium / f'product_logo_{size}.png').exists():
            _png(size, chromium / f'product_logo_{size}.png')
    # Linux packages (desktop entry, menus).
    for path in sorted((chromium / 'linux').glob('product_logo_*.png')):
        _png(int(path.stem.rsplit('_', 1)[1]), path)
    if (chromium / 'linux/product_logo_32.xpm').exists():
        _xpm(32, chromium / 'linux/product_logo_32.xpm')
    # Status tray (monochrome).
    _png(22, chromium / 'product_logo_22_mono.png', fill='#121212')
    # WebUI pages (profile picker, first run...): the vector logo itself.
    for name in ('product_logo.svg', 'product_logo_animation.svg'):
        (chromium / name).write_text(LOGO.read_text())
    for size in (16, 32):
        linux_logo = theme / 'default_100_percent/chromium/linux' / f'product_logo_{size}.png'
        if linux_logo.exists():
            _png(size, linux_logo)
    for scale, folder in ((1, 'default_100_percent'), (2, 'default_200_percent')):
        for size in (16, 32):
            _png(size * scale, theme / folder / 'chromium' / f'product_logo_{size}.png')
        _wordmark(22 * scale, (32, 24, 12, 255), theme / folder / 'chromium' / 'product_logo_name_22.png')
        _wordmark(22 * scale, (255, 255, 255, 255),
                  theme / folder / 'chromium' / 'product_logo_name_22_white.png')
    _png(600, chromium / 'win/tiles/Logo.png')
    _png(176, chromium / 'win/tiles/SmallLogo.png')
    # .ico for the executable, the app list and the installers.
    for name in ('chromium.ico', 'app_list.ico'):
        _ico(chromium / 'win' / name)
    _ico(src / 'chrome/installer/setup/setup.ico')
    _ico(src / 'chrome/installer/mini_installer/mini_installer.ico')
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
