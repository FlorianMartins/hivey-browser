"""Hivey's profile pictures: 29 avatars drawn here, in three styles, in place
of Chromium's "modern" avatars (the same files and resource ids, 27 to 55):

- fun (27-37): round mascots with big eyes (the Hivey bee, a robot...);
- serious (38-47): an emblem (Phosphor Icons, MIT, fill weight) in white on
  a deep gradient;
- sober (48-55): plain shapes in quiet colors.

Each is rendered at 96 px (100 %) and 192 px (200 %). Labels go to the
profile picker (profiles_strings.grdp), in English and French.
"""
import re
from pathlib import Path

# Slot -> (Chromium file, style, id, English label, French label).
SLOTS = [
    (27, 'origami/avatar_cat.png', 'fun', 'bee', 'Bee', 'Abeille'),
    (28, 'origami/avatar_corgi.png', 'fun', 'robot', 'Robot', 'Robot'),
    (29, 'origami/avatar_dragon.png', 'fun', 'ghost', 'Ghost', 'Fantôme'),
    (30, 'origami/avatar_elephant.png', 'fun', 'alien', 'Alien', 'Extraterrestre'),
    (31, 'origami/avatar_fox.png', 'fun', 'fox', 'Fox', 'Renard'),
    (32, 'origami/avatar_monkey.png', 'fun', 'cat', 'Cat', 'Chat'),
    (33, 'origami/avatar_panda.png', 'fun', 'panda', 'Panda', 'Panda'),
    (34, 'origami/avatar_penguin.png', 'fun', 'frog', 'Frog', 'Grenouille'),
    (35, 'origami/avatar_pinkbutterfly.png', 'fun', 'monster', 'Monster', 'Monstre'),
    (36, 'origami/avatar_rabbit.png', 'fun', 'octopus', 'Octopus', 'Pieuvre'),
    (37, 'origami/avatar_unicorn.png', 'fun', 'astronaut', 'Astronaut', 'Astronaute'),
    (38, 'illustration/avatar_basketball.png', 'serious', 'hexagon', 'Hive', 'Ruche'),
    (39, 'illustration/avatar_bike.png', 'serious', 'briefcase', 'Work', 'Travail'),
    (40, 'illustration/avatar_bird.png', 'serious', 'shield-check', 'Shield', 'Bouclier'),
    (41, 'illustration/avatar_cheese.png', 'serious', 'compass', 'Compass', 'Boussole'),
    (42, 'illustration/avatar_football.png', 'serious', 'mountains', 'Mountains', 'Montagnes'),
    (43, 'illustration/avatar_ramen.png', 'serious', 'lightning', 'Lightning', 'Éclair'),
    (44, 'illustration/avatar_sunglasses.png', 'serious', 'atom', 'Atom', 'Atome'),
    (45, 'illustration/avatar_sushi.png', 'serious', 'planet', 'Planet', 'Planète'),
    (46, 'illustration/avatar_tamagotchi.png', 'serious', 'rocket-launch', 'Rocket', 'Fusée'),
    (47, 'illustration/avatar_vinyl.png', 'serious', 'terminal-window', 'Code', 'Code'),
    (48, 'abstract/avatar_avocado.png', 'sober', 'dot', 'Dot', 'Point'),
    (49, 'abstract/avatar_cappuccino.png', 'sober', 'ring', 'Ring', 'Anneau'),
    (50, 'abstract/avatar_icecream.png', 'sober', 'split', 'Two tones', 'Deux tons'),
    (51, 'abstract/avatar_icewater.png', 'sober', 'stripe', 'Stripe', 'Bande'),
    (52, 'abstract/avatar_melon.png', 'sober', 'waves', 'Waves', 'Vagues'),
    (53, 'abstract/avatar_onigiri.png', 'sober', 'hex-outline', 'Outline', 'Contour'),
    (54, 'abstract/avatar_pizza.png', 'sober', 'aurora', 'Aurora', 'Aurore'),
    (55, 'abstract/avatar_sandwich.png', 'sober', 'night', 'Night', 'Nuit'),
]

SIZE = 192  # drawing units; rendered at 96 and 192 px


def _svg(body, defs=''):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
            f'viewBox="0 0 {SIZE} {SIZE}"><defs>{defs}</defs>{body}</svg>')


def _background(top, bottom, gid='bg'):
    defs = (f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>')
    return defs, f'<circle cx="96" cy="96" r="96" fill="url(#{gid})"/>'


def _eyes(y, dx=26, r=15, x=96):
    """Two big round eyes with a highlight each."""
    out = ''
    for cx in (x - dx, x + dx):
        out += (f'<circle cx="{cx}" cy="{y}" r="{r}" fill="#fff"/>'
                f'<circle cx="{cx + 2}" cy="{y + 2}" r="{r * 0.58:.1f}" fill="#1b1b2f"/>'
                f'<circle cx="{cx + 6}" cy="{y - 3}" r="{r * 0.22:.1f}" fill="#fff"/>')
    return out


def _smile(y, w=16, color='#1b1b2f', x=96):
    return (f'<path d="M{x - w} {y} Q{x} {y + w * 0.9} {x + w} {y}" fill="none" stroke="{color}" '
            f'stroke-width="5" stroke-linecap="round"/>')


def _cheeks(y, dx=46, color='#ff7aa8'):
    return ''.join(f'<ellipse cx="{96 + s * dx}" cy="{y}" rx="10" ry="6" fill="{color}" opacity=".55"/>'
                   for s in (-1, 1))


def _fun(kind):
    if kind == 'bee':
        defs, bg = _background('#6366f1', '#8b5cf6')
        body = (bg + '<ellipse cx="62" cy="62" rx="26" ry="18" fill="#e0f2fe" opacity=".85" transform="rotate(-25 62 62)"/>'
                '<ellipse cx="130" cy="62" rx="26" ry="18" fill="#e0f2fe" opacity=".85" transform="rotate(25 130 62)"/>'
                '<circle cx="96" cy="108" r="56" fill="#fcd34d"/>'
                '<path d="M44 120 Q96 140 148 120 L146 134 Q96 154 46 134 Z" fill="#1b1b2f"/>'
                '<path d="M74 52 Q66 30 56 26" stroke="#1b1b2f" stroke-width="5" fill="none" stroke-linecap="round"/>'
                '<path d="M118 52 Q126 30 136 26" stroke="#1b1b2f" stroke-width="5" fill="none" stroke-linecap="round"/>'
                '<circle cx="56" cy="26" r="6" fill="#1b1b2f"/><circle cx="136" cy="26" r="6" fill="#1b1b2f"/>'
                + _eyes(96) + _cheeks(112) + _smile(112, 12))
    elif kind == 'robot':
        defs, bg = _background('#0ea5e9', '#6366f1')
        body = (bg + '<line x1="96" y1="44" x2="96" y2="26" stroke="#cbd5e1" stroke-width="6"/>'
                '<circle cx="96" cy="22" r="9" fill="#f472b6"/>'
                '<rect x="40" y="44" width="112" height="100" rx="30" fill="#e2e8f0"/>'
                '<rect x="54" y="62" width="84" height="56" rx="18" fill="#1e293b"/>'
                '<circle cx="78" cy="88" r="10" fill="#5eead4"/><circle cx="114" cy="88" r="10" fill="#5eead4"/>'
                '<path d="M80 106 Q96 116 112 106" stroke="#5eead4" stroke-width="5" fill="none" stroke-linecap="round"/>'
                '<rect x="28" y="80" width="12" height="28" rx="6" fill="#94a3b8"/>'
                '<rect x="152" y="80" width="12" height="28" rx="6" fill="#94a3b8"/>'
                '<rect x="70" y="150" width="52" height="20" rx="8" fill="#cbd5e1"/>')
    elif kind == 'ghost':
        defs, bg = _background('#7c3aed', '#c026d3')
        body = (bg + '<path d="M46 150 V92 a50 50 0 0 1 100 0 V150 l-16 -12 -17 12 -17 -12 -17 12 -17 -12 Z" fill="#f8fafc"/>'
                + _eyes(92, dx=22, r=13) + _cheeks(110, dx=38) + '<ellipse cx="96" cy="118" rx="8" ry="10" fill="#1b1b2f"/>')
    elif kind == 'alien':
        defs, bg = _background('#14b8a6', '#4f46e5')
        body = (bg + '<path d="M70 50 L58 24" stroke="#86efac" stroke-width="6" stroke-linecap="round"/>'
                '<path d="M122 50 L134 24" stroke="#86efac" stroke-width="6" stroke-linecap="round"/>'
                '<circle cx="58" cy="22" r="8" fill="#fde047"/><circle cx="134" cy="22" r="8" fill="#fde047"/>'
                '<ellipse cx="96" cy="100" rx="56" ry="60" fill="#86efac"/>'
                '<ellipse cx="72" cy="94" rx="18" ry="24" fill="#1b1b2f" transform="rotate(-20 72 94)"/>'
                '<ellipse cx="120" cy="94" rx="18" ry="24" fill="#1b1b2f" transform="rotate(20 120 94)"/>'
                '<circle cx="76" cy="86" r="5" fill="#fff"/><circle cx="124" cy="86" r="5" fill="#fff"/>'
                + _smile(132, 10))
    elif kind == 'fox':
        defs, bg = _background('#f59e0b', '#ef4444')
        body = (bg + '<path d="M44 48 L70 96 L40 100 Z" fill="#ea580c"/><path d="M148 48 L122 96 L152 100 Z" fill="#ea580c"/>'
                '<path d="M40 92 Q96 46 152 92 Q150 150 96 164 Q42 150 40 92 Z" fill="#fb923c"/>'
                '<path d="M52 110 Q96 118 140 110 Q130 156 96 164 Q62 156 52 110 Z" fill="#fff7ed"/>'
                + _eyes(100, dx=26, r=12) + '<ellipse cx="96" cy="128" rx="9" ry="7" fill="#1b1b2f"/>')
    elif kind == 'cat':
        defs, bg = _background('#f472b6', '#a855f7')
        body = (bg + '<path d="M46 60 L60 104 L90 76 Z" fill="#fde68a"/><path d="M146 60 L132 104 L102 76 Z" fill="#fde68a"/>'
                '<circle cx="96" cy="112" r="54" fill="#fde68a"/>'
                + _eyes(106, dx=24, r=12) + _cheeks(124, dx=38)
                + '<path d="M90 124 L102 124 L96 131 Z" fill="#f472b6"/>'
                '<path d="M60 128 H30 M62 136 H34 M132 128 H162 M130 136 H158" stroke="#b45309" stroke-width="3" stroke-linecap="round"/>')
    elif kind == 'panda':
        defs, bg = _background('#22c55e', '#0d9488')
        body = (bg + '<circle cx="54" cy="58" r="20" fill="#1b1b2f"/><circle cx="138" cy="58" r="20" fill="#1b1b2f"/>'
                '<circle cx="96" cy="106" r="58" fill="#f8fafc"/>'
                '<ellipse cx="72" cy="100" rx="17" ry="21" fill="#1b1b2f" transform="rotate(-25 72 100)"/>'
                '<ellipse cx="120" cy="100" rx="17" ry="21" fill="#1b1b2f" transform="rotate(25 120 100)"/>'
                '<circle cx="74" cy="98" r="7" fill="#fff"/><circle cx="118" cy="98" r="7" fill="#fff"/>'
                '<ellipse cx="96" cy="126" rx="10" ry="7" fill="#1b1b2f"/>' + _smile(136, 9))
    elif kind == 'frog':
        defs, bg = _background('#38bdf8', '#2563eb')
        body = (bg + '<circle cx="64" cy="70" r="24" fill="#4ade80"/><circle cx="128" cy="70" r="24" fill="#4ade80"/>'
                '<ellipse cx="96" cy="118" rx="62" ry="46" fill="#4ade80"/>'
                + _eyes(70, dx=32, r=14) + _cheeks(124, dx=44)
                + '<path d="M66 124 Q96 150 126 124" stroke="#166534" stroke-width="5" fill="none" stroke-linecap="round"/>')
    elif kind == 'monster':
        defs, bg = _background('#facc15', '#f97316')
        body = (bg + '<path d="M60 56 L52 26 L76 48 Z" fill="#fef3c7"/><path d="M132 56 L140 26 L116 48 Z" fill="#fef3c7"/>'
                '<path d="M40 110 Q40 46 96 46 Q152 46 152 110 Q152 164 96 164 Q40 164 40 110 Z" fill="#8b5cf6"/>'
                '<circle cx="96" cy="96" r="26" fill="#fff"/><circle cx="100" cy="100" r="14" fill="#1b1b2f"/>'
                '<circle cx="106" cy="92" r="5" fill="#fff"/>'
                '<path d="M70 132 Q96 152 122 132 Z" fill="#1b1b2f"/>'
                '<path d="M82 134 L86 142 L90 134 M102 134 L106 142 L110 134" fill="#fff"/>')
    elif kind == 'octopus':
        defs, bg = _background('#06b6d4', '#7c3aed')
        legs = ''.join(f'<path d="M{x} 128 q{d} 30 {d * 2} 34" stroke="#fb7185" stroke-width="13" fill="none" '
                       f'stroke-linecap="round"/>' for x, d in ((62, -8), (82, -4), (110, 4), (130, 8)))
        body = (bg + legs + '<ellipse cx="96" cy="96" rx="54" ry="50" fill="#fb7185"/>'
                + _eyes(94, dx=22, r=13) + _cheeks(112, dx=38, color='#fde68a') + _smile(116, 10))
    else:  # astronaut
        defs, bg = _background('#1e1b4b', '#4338ca')
        defs += ('<linearGradient id="visor" x1="0" y1="0" x2="1" y2="1">'
                 '<stop offset="0" stop-color="#67e8f9"/><stop offset="1" stop-color="#7c3aed"/></linearGradient>')
        stars = ''.join(f'<circle cx="{x}" cy="{y}" r="2.5" fill="#fff" opacity=".8"/>'
                        for x, y in ((30, 60), (160, 50), (150, 150), (40, 140), (100, 20)))
        body = (bg + stars + '<circle cx="96" cy="100" r="58" fill="#f1f5f9"/>'
                '<rect x="54" y="74" width="84" height="56" rx="26" fill="url(#visor)"/>'
                '<path d="M66 86 Q76 78 90 80" stroke="#fff" stroke-width="5" fill="none" stroke-linecap="round" opacity=".8"/>'
                '<rect x="80" y="150" width="32" height="14" rx="5" fill="#cbd5e1"/>')
    return _svg(body, defs)


# Deep, calm gradients for the emblems, in the browser's palette.
SERIOUS_GRADIENTS = [('#4f46e5', '#7c3aed'), ('#0f172a', '#334155'), ('#065f46', '#0d9488'),
                     ('#1e3a8a', '#2563eb'), ('#3f3f46', '#71717a'), ('#7c2d12', '#c2410c'),
                     ('#312e81', '#0e7490'), ('#581c87', '#be185d'), ('#111827', '#4338ca'),
                     ('#14532d', '#15803d')]


def _serious(kind, index, phosphor_fill):
    top, bottom = SERIOUS_GRADIENTS[index % len(SERIOUS_GRADIENTS)]
    defs, bg = _background(top, bottom)
    if kind == 'hexagon':
        glyph = '<path d="M96 42 L143 69 L143 123 L96 150 L49 123 L49 69 Z" fill="#fff"/>' \
                '<path d="M96 66 L122 81 L122 111 L96 126 L70 111 L70 81 Z" fill="none" stroke="#6366f1" stroke-width="8"/>'
    else:
        svg = (phosphor_fill / f'{kind}-fill.svg').read_text()
        inner = re.sub(r'^.*?<svg[^>]*>|</svg>\s*$', '', svg, flags=re.S).replace('currentColor', '#ffffff')
        glyph = f'<g transform="translate(48 48) scale(0.375)" fill="#ffffff">{inner}</g>'
    return _svg(bg + '<circle cx="96" cy="96" r="84" fill="none" stroke="#fff" stroke-opacity=".18" stroke-width="2"/>'
                + glyph, defs)


def _sober(kind):
    if kind == 'dot':
        return _svg('<circle cx="96" cy="96" r="96" fill="#e7e5e4"/><circle cx="96" cy="96" r="22" fill="#57534e"/>')
    if kind == 'ring':
        return _svg('<circle cx="96" cy="96" r="96" fill="#1f2937"/>'
                    '<circle cx="96" cy="96" r="44" fill="none" stroke="#9ca3af" stroke-width="12"/>')
    if kind == 'split':
        return _svg('<clipPath id="c"><circle cx="96" cy="96" r="96"/></clipPath>'
                    '<g clip-path="url(#c)"><rect width="192" height="192" fill="#cbd5e1"/>'
                    '<path d="M0 192 L192 0 L192 192 Z" fill="#475569"/></g>')
    if kind == 'stripe':
        return _svg('<clipPath id="c"><circle cx="96" cy="96" r="96"/></clipPath>'
                    '<g clip-path="url(#c)"><rect width="192" height="192" fill="#f5f5f4"/>'
                    '<rect x="0" y="80" width="192" height="32" fill="#6366f1"/></g>')
    if kind == 'waves':
        return _svg('<clipPath id="c"><circle cx="96" cy="96" r="96"/></clipPath>'
                    '<g clip-path="url(#c)"><rect width="192" height="192" fill="#e0f2fe"/>'
                    '<path d="M0 110 Q48 86 96 110 T192 110 V192 H0 Z" fill="#7dd3fc"/>'
                    '<path d="M0 140 Q48 116 96 140 T192 140 V192 H0 Z" fill="#0284c7"/></g>')
    if kind == 'hex-outline':
        return _svg('<circle cx="96" cy="96" r="96" fill="#fafaf9"/>'
                    '<path d="M96 46 L139 71 L139 121 L96 146 L53 121 L53 71 Z" fill="none" stroke="#44403c" stroke-width="8"/>')
    if kind == 'aurora':
        defs = ('<radialGradient id="a" cx=".3" cy=".3" r=".9"><stop offset="0" stop-color="#a5b4fc"/>'
                '<stop offset=".55" stop-color="#8b5cf6"/><stop offset="1" stop-color="#1e1b4b"/></radialGradient>')
        return _svg('<circle cx="96" cy="96" r="96" fill="url(#a)"/>', defs)
    # night
    return _svg('<circle cx="96" cy="96" r="96" fill="#0f172a"/>'
                '<path d="M118 52 a48 48 0 1 0 22 80 a40 40 0 1 1 -22 -80 Z" fill="#e2e8f0"/>')


def render(phosphor_fill, out_100, out_200, cairosvg):
    """Writes every avatar's PNGs; returns {slot: (en, fr)} for the labels."""
    labels = {}
    serious = 0
    for slot, path, style, kind, en, fr in SLOTS:
        if style == 'fun':
            svg = _fun(kind)
        elif style == 'serious':
            svg = _serious(kind, serious, phosphor_fill)
            serious += 1
        else:
            svg = _sober(kind)
        for out, px in ((out_100, 96), (out_200, 192)):
            target = out / path
            target.parent.mkdir(parents=True, exist_ok=True)
            cairosvg.svg2png(bytestring=svg.encode(), write_to=str(target), output_width=px, output_height=px)
        labels[slot] = (en, fr)
    return labels
