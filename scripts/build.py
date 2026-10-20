#!/usr/bin/env python3
"""Builds every SVG used by the profile README.

Static art (hero, cards, buttons, headers) plus a live stats panel pulled
from the GitHub GraphQL API. Fonts are subset and embedded so the art looks
identical everywhere GitHub renders it.

Run locally:  GITHUB_TOKEN=$(gh auth token) python3 scripts/build.py
"""
import base64, html, io, json, os, sys, urllib.request, datetime
from fontTools.ttLib import TTFont
from fontTools import subset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
FONT_DIR = os.path.join(OUT, "fonts")
USER = os.environ.get("PROFILE_USER", "arafatomer66")

FONTS = {
    "Geist": "Geist.woff2",
    "Geist Mono": "GeistMono.woff2",
    "Noto Sans Bengali": "NotoSansBengali.woff2",
}

# ── design tokens ────────────────────────────────────────────────────────
BG = "#050505"
CORE_A, CORE_B = "#0F0F12", "#08080A"
TEXT, MUTED, DIM = "#F4F4F5", "#A1A1AA", "#6B6B73"
HAIR = "rgba(255,255,255,0.08)"
EASE = "cubic-bezier(0.32,0.72,0,1)"

_font_cache = {}


def font(family):
    if family not in _font_cache:
        _font_cache[family] = TTFont(os.path.join(FONT_DIR, FONTS[family]))
    return _font_cache[family]


def measure(s, size, family="Geist", weight=400, ls=0.0):
    f = font(family)
    cmap, hmtx = f.getBestCmap(), f["hmtx"]
    upm = f["head"].unitsPerEm
    w = 0
    for ch in s:
        g = cmap.get(ord(ch))
        w += hmtx[g][0] if g else upm * 0.5
    w = w / upm * size
    if family == "Geist":
        w *= 1 + (weight - 400) * 0.00035
    return w + ls * len(s)


def wrap(s, maxw, size, family="Geist", weight=400, ls=0.0):
    lines, cur = [], ""
    for word in s.split():
        t = (cur + " " + word).strip()
        if measure(t, size, family, weight, ls) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def esc(s):
    return html.escape(s, quote=True)


class Svg:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts, self.defs, self.css = [], [], []
        self.chars = {k: set() for k in FONTS}
        self._id = 0

    def uid(self, p="i"):
        self._id += 1
        return f"{p}{self._id}"

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size, weight=400, fill=TEXT, family="Geist",
             ls=0.0, anchor="start", opacity=None, extra=""):
        self.chars[family].update(s)
        op = f' opacity="{opacity}"' if opacity is not None else ""
        fam = {"Geist": "g", "Geist Mono": "m", "Noto Sans Bengali": "b"}[family]
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" class="{fam}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" letter-spacing="{ls}" '
            f'text-anchor="{anchor}"{op} {extra}>{esc(s)}</text>')

    def _faces(self):
        out = []
        for fam, used in self.chars.items():
            if not used:
                continue
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["*"]
            opts.name_IDs = []
            opts.notdef_outline = True
            sub = subset.Subsetter(opts)
            f = TTFont(os.path.join(FONT_DIR, FONTS[fam]))
            sub.populate(text="".join(sorted(used)) + " ")
            sub.subset(f)
            buf = io.BytesIO()
            f.flavor = "woff2"
            f.save(buf)
            b64 = base64.b64encode(buf.getvalue()).decode()
            out.append(
                f"@font-face{{font-family:'{fam} Sub';src:url(data:font/woff2;base64,{b64}) format('woff2');"
                f"font-weight:100 900;}}")
        return "".join(out)

    def render(self):
        css = (
            self._faces()
            + ".g{font-family:'Geist Sub',ui-sans-serif,system-ui,sans-serif}"
            + ".m{font-family:'Geist Mono Sub',ui-monospace,monospace}"
            + ".b{font-family:'Noto Sans Bengali Sub',sans-serif}"
            + f"@keyframes up{{from{{opacity:0;transform:translateY(26px)}}to{{opacity:1;transform:none}}}}"
            + f".up{{animation:up 1.2s {EASE} both}}"
            + "@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}"
            + "".join(self.css)
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" fill="none">'
            f"<style>{css}</style><defs>{''.join(self.defs)}</defs>"
            + "".join(self.parts) + "</svg>")

    def save(self, name):
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.render())
        print(f"  {name:28s} {os.path.getsize(path)/1024:6.1f} KB")


# ── shared pieces ────────────────────────────────────────────────────────
def glow(svg, cx, cy, r, color, alpha, drift=None):
    gid = svg.uid("glow")
    svg.defs.append(
        f'<radialGradient id="{gid}"><stop offset="0" stop-color="{color}" stop-opacity="{alpha}"/>'
        f'<stop offset="0.55" stop-color="{color}" stop-opacity="{alpha*0.35:.3f}"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')
    anim = ""
    if drift:
        dx, dy, dur = drift
        anim = (f'<animateTransform attributeName="transform" type="translate" '
                f'values="0 0;{dx} {dy};0 0" dur="{dur}s" repeatCount="indefinite" '
                f'calcMode="spline" keySplines="0.45 0 0.55 1;0.45 0 0.55 1"/>')
    svg.add(f'<g><circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{gid})"/>{anim}</g>')


def bezel(svg, x, y, w, h, r=40, pad=8):
    """Double-bezel: hairline outer tray + machined inner core. Returns the
    inner core rect and a clip id for the core."""
    core = svg.uid("core")
    hl = svg.uid("hl")
    clip = svg.uid("clip")
    svg.defs.append(
        f'<linearGradient id="{core}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{CORE_A}"/><stop offset="1" stop-color="{CORE_B}"/></linearGradient>'
        f'<linearGradient id="{hl}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#fff" stop-opacity="0.16"/>'
        f'<stop offset="0.18" stop-color="#fff" stop-opacity="0.03"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0.02"/></linearGradient>')
    ix, iy, iw, ih, ir = x + pad, y + pad, w - 2 * pad, h - 2 * pad, r - pad
    svg.defs.append(f'<clipPath id="{clip}"><rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" rx="{ir}"/></clipPath>')
    svg.add(f'<rect x="{x+.75}" y="{y+.75}" width="{w-1.5}" height="{h-1.5}" rx="{r}" '
            f'fill="#141417" stroke="rgba(255,255,255,0.09)" stroke-width="1.5"/>')
    svg.add(f'<rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" rx="{ir}" fill="url(#{core})"/>')
    return (ix, iy, iw, ih, ir, clip, hl)


def bezel_highlight(svg, inner):
    ix, iy, iw, ih, ir, clip, hl = inner
    svg.add(f'<rect x="{ix+.75}" y="{iy+.75}" width="{iw-1.5}" height="{ih-1.5}" rx="{ir}" '
            f'stroke="url(#{hl})" stroke-width="1.5"/>')


def grain(svg, x, y, w, h, clip, opacity=0.05):
    fid = svg.uid("grain")
    svg.defs.append(
        f'<filter id="{fid}" x="0" y="0" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/>'
        f'<feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1 0"/></filter>')
    svg.add(f'<g clip-path="url(#{clip})"><rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'filter="url(#{fid})" opacity="{opacity}"/></g>')


def grid(svg, x, y, w, h, clip, step=64, cx=None, cy=None):
    mid = svg.uid("gm")
    rg = svg.uid("rg")
    cx = cx if cx is not None else x + w * 0.7
    cy = cy if cy is not None else y + h * 0.3
    svg.defs.append(
        f'<radialGradient id="{rg}" cx="{cx}" cy="{cy}" r="{max(w,h)*0.55}" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="#fff" stop-opacity="1"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="{mid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{rg})"/></mask>')
    lines = []
    gx = x + (w % step) / 2
    while gx < x + w:
        lines.append(f"M{gx:.1f} {y}V{y+h}")
        gx += step
    gy = y + (h % step) / 2
    while gy < y + h:
        lines.append(f"M{x} {gy:.1f}H{x+w}")
        gy += step
    svg.add(f'<g clip-path="url(#{clip})" mask="url(#{mid})"><path d="{"".join(lines)}" '
            f'stroke="#fff" stroke-opacity="0.045" stroke-width="1"/></g>')


def eyebrow(svg, x, y, label, dot=None, size=17, anchor_right=False):
    w = measure(label, size, "Geist Mono", 500, 2.6) + (60 if dot else 40)
    if anchor_right:
        x = x - w
    h = size + 22
    svg.add(f'<rect x="{x}" y="{y}" width="{w:.1f}" height="{h}" rx="{h/2}" '
            f'fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.10)"/>')
    tx = x + 20
    if dot:
        svg.add(f'<circle cx="{x+22}" cy="{y+h/2}" r="4.5" fill="{dot}"/>')
        tx = x + 38
    svg.text(tx, y + h / 2 + size * 0.36, label.upper(), size, 500, "#C9C9D1", "Geist Mono", 2.6)
    return w


def arrow_button(svg, cx, cy, r=30, light=False):
    fill = "#F4F4F5" if light else "rgba(255,255,255,0.06)"
    stroke = "none" if light else "rgba(255,255,255,0.12)"
    col = "#050505" if light else "#E4E4E7"
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
    a = r * 0.3
    svg.add(f'<path d="M{cx-a} {cy+a}L{cx+a} {cy-a}M{cx-a*0.55} {cy-a}H{cx+a}V{cy+a*0.55}" '
            f'stroke="{col}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')


def tag_row(svg, x, y, tags, size=16, maxw=None):
    cx = x
    for t in tags:
        w = measure(t, size, "Geist Mono", 400, 0.4) + 32
        if maxw and cx + w > x + maxw:
            break
        svg.add(f'<rect x="{cx:.1f}" y="{y}" width="{w:.1f}" height="38" rx="19" '
                f'fill="rgba(255,255,255,0.035)" stroke="rgba(255,255,255,0.09)"/>')
        svg.text(cx + 16, y + 25, t, size, 400, "#BDBDC6", "Geist Mono", 0.4)
        cx += w + 10


# ── hero ─────────────────────────────────────────────────────────────────
def build_hero():
    W, H = 1600, 780
    s = Svg(W, H)
    inner = bezel(s, 0, 0, W, H, r=48, pad=10)
    ix, iy, iw, ih, ir, clip, _ = inner
    s.add(f'<g clip-path="url(#{clip})">')
    glow(s, 1300, 120, 520, "#10B981", 0.30, (-60, 40, 22))
    glow(s, 260, 760, 560, "#7C3AED", 0.26, (70, -30, 26))
    glow(s, 900, -80, 380, "#3B82F6", 0.20, (40, 30, 19))
    s.add("</g>")
    grid(s, ix, iy, iw, ih, clip, 64, 1250, 170)
    grain(s, ix, iy, iw, ih, clip, 0.05)

    pad = 84
    # top bar
    s.add('<g class="up" style="animation-delay:.05s">')
    s.add(f'<rect x="{pad}" y="70" width="58" height="58" rx="18" fill="#F4F4F5"/>')
    s.text(pad + 29, 108, "OA", 24, 600, "#050505", "Geist", -0.6, "middle")
    s.text(pad + 80, 95, "Md Omer Arafat", 20, 500, TEXT, "Geist", -0.2)
    s.text(pad + 80, 120, "omerarafat.com", 17, 400, DIM, "Geist Mono", 0.2)
    # status pill
    label = "OPEN TO SELECT PROJECTS"
    pw = measure(label, 16, "Geist Mono", 500, 2.4) + 66
    px = W - pad - pw
    s.add(f'<rect x="{px:.1f}" y="73" width="{pw:.1f}" height="52" rx="26" fill="rgba(16,185,129,0.08)" stroke="rgba(16,185,129,0.30)"/>')
    s.add(f'<circle cx="{px+28:.1f}" cy="99" r="11" fill="#10B981" opacity=".18" style="animation:blink 2.4s {EASE} infinite"/>')
    s.add(f'<circle cx="{px+28:.1f}" cy="99" r="5" fill="#34D399"/>')
    s.text(px + 46, 105, label, 16, 500, "#A7F3D0", "Geist Mono", 2.4)
    s.add("</g>")

    s.add('<g class="up" style="animation-delay:.18s">')
    eyebrow(s, pad, 222, "Senior Software Engineer  ·  Founder", dot="#A78BFA")
    s.add("</g>")

    s.add('<g class="up" style="animation-delay:.3s">')
    gid = s.uid("ng")
    s.defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
                  f'<stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#B4B4BC"/></linearGradient>')
    s.text(pad - 6, 390, "Md Omer Arafat", 150, 500, f"url(#{gid})", "Geist", -6.5)
    s.add("</g>")

    s.add('<g class="up" style="animation-delay:.42s">')
    s.text(pad, 462, "I design and ship products end to end, across web, mobile,", 34, 400, MUTED, "Geist", -0.4)
    s.text(pad, 508, "cloud infrastructure and identity. Eight years and counting.", 34, 400, MUTED, "Geist", -0.4)
    s.add("</g>")

    # meta row
    s.add('<g class="up" style="animation-delay:.56s">')
    s.add(f'<path d="M{pad} 590H{W-pad}" stroke="rgba(255,255,255,0.09)" stroke-width="1.5"/>')
    cols = [
        ("Currently", "Allianz Australia"),
        ("Building", "ShareDeal"),
        ("Based in", "Dhaka, Bangladesh"),
        ("Clients in", "Australia · Germany · USA +"),
    ]
    cw = (W - 2 * pad) / 4
    for i, (k, v) in enumerate(cols):
        x = pad + i * cw
        if i:
            s.add(f'<path d="M{x-24:.1f} 626V708" stroke="rgba(255,255,255,0.07)" stroke-width="1.5"/>')
        s.text(x, 650, k.upper(), 17, 500, DIM, "Geist Mono", 2.6)
        s.text(x, 694, v, 28, 500, TEXT, "Geist", -0.5)
    s.add("</g>")
    bezel_highlight(s, inner)
    s.save("hero.svg")


# ── buttons ──────────────────────────────────────────────────────────────
def build_button(name, label, primary=False):
    size = 30
    tw = measure(label, size, "Geist", 500, -0.3)
    H = 92
    W = int(tw + 44 + 12 + 68 + 14)
    s = Svg(W, H)
    if primary:
        s.add(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="{(H-2)/2}" fill="#F4F4F5" stroke="rgba(0,0,0,0.12)" stroke-width="2"/>')
        s.text(44, H / 2 + 10.5, label, size, 500, "#050505", "Geist", -0.3)
        cx = W - 14 - 34
        s.add(f'<circle cx="{cx}" cy="{H/2}" r="32" fill="#050505"/>')
        a = 9
        s.add(f'<path d="M{cx-a} {H/2+a}L{cx+a} {H/2-a}M{cx-a*0.5} {H/2-a}H{cx+a}V{H/2+a*0.5}" stroke="#F4F4F5" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        s.add(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="{(H-2)/2}" fill="#0C0C0E" stroke="rgba(255,255,255,0.14)" stroke-width="2"/>')
        s.add(f'<rect x="3" y="3" width="{W-6}" height="{H-6}" rx="{(H-6)/2}" stroke="rgba(255,255,255,0.06)" stroke-width="1.5"/>')
        s.text(44, H / 2 + 10.5, label, size, 500, TEXT, "Geist", -0.3)
        cx = W - 14 - 34
        s.add(f'<circle cx="{cx}" cy="{H/2}" r="32" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.10)"/>')
        a = 9
        s.add(f'<path d="M{cx-a} {H/2+a}L{cx+a} {H/2-a}M{cx-a*0.5} {H/2-a}H{cx+a}V{H/2+a*0.5}" stroke="#E4E4E7" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>')
    s.save(f"btn-{name}.svg")


# ── section headers (dark + light variants) ──────────────────────────────
def build_header(name, index, label, title, note):
    for mode in ("dark", "light"):
        W, H = 1600, 230
        s = Svg(W, H)
        fg = "#F4F4F5" if mode == "dark" else "#0A0A0B"
        mut = "#8B8B93" if mode == "dark" else "#6B6B73"
        pill_fill = "rgba(255,255,255,0.04)" if mode == "dark" else "rgba(0,0,0,0.035)"
        pill_stroke = "rgba(255,255,255,0.12)" if mode == "dark" else "rgba(0,0,0,0.10)"
        lab = f"{index}  /  {label}".upper()
        pw = measure(lab, 17, "Geist Mono", 500, 2.6) + 40
        s.add(f'<rect x="8" y="58" width="{pw:.1f}" height="40" rx="20" fill="{pill_fill}" stroke="{pill_stroke}"/>')
        s.text(28, 84, lab, 17, 500, mut, "Geist Mono", 2.6)
        s.text(4, 186, title, 68, 500, fg, "Geist", -2.6)
        s.text(W - 8, 186, note, 22, 400, mut, "Geist", -0.2, "end")
        s.save(f"h-{name}-{mode}.svg")


# ── project cards ────────────────────────────────────────────────────────
CARD_H = 540
GUT = 12  # half-gutter baked into each card's transparent margin


def build_card(name, width, idx, category, title, desc, tags, accent,
               accent2=None, bengali=None, height=CARD_H, visual=None):
    W, H = width, height
    s = Svg(W, H)
    inner = bezel(s, GUT, GUT, W - 2 * GUT, H - 2 * GUT, r=44, pad=8)
    ix, iy, iw, ih, ir, clip, _ = inner
    s.add(f'<g clip-path="url(#{clip})">')
    glow(s, ix + iw - 40, iy + 10, min(iw, 560) * 0.95, accent, 0.30, (-30, 25, 20))
    if accent2:
        glow(s, ix + 40, iy + ih + 40, min(iw, 520) * 0.8, accent2, 0.16, (30, -20, 24))
    s.add("</g>")
    grain(s, ix, iy, iw, ih, clip, 0.045)
    if visual:
        visual(s, inner)

    p = 48
    x0, y0 = ix + p, iy + p
    # eyebrow
    s.add(f'<circle cx="{x0+5}" cy="{y0+14}" r="5" fill="{accent}"/>')
    s.text(x0 + 22, y0 + 20, f"{idx}  /  {category}".upper(), 16, 500, "#8E8E97", "Geist Mono", 2.6)
    arrow_button(s, ix + iw - p - 26, y0 + 14, 30)

    ty = y0 + 118
    tx = x0
    if bengali:
        s.text(tx, ty, bengali, 54, 500, TEXT, "Noto Sans Bengali", 0)
        tx += measure(bengali, 54, "Geist") * 0 + bengali_width(bengali, 54) + 22
        s.text(tx, ty, "·", 54, 400, DIM, "Geist")
        tx += 34
    s.text(tx, ty, title, 54, 500, TEXT, "Geist", -2.0)

    text_w = iw - 2 * p if not visual else iw * 0.52 - p
    lines = wrap(desc, text_w, 25, "Geist", 400, -0.2)
    for i, ln in enumerate(lines[:4]):
        s.text(x0, ty + 62 + i * 37, ln, 25, 400, MUTED, "Geist", -0.2)

    tag_row(s, x0, iy + ih - p - 38, tags, 16, iw - 2 * p)
    bezel_highlight(s, inner)
    s.save(f"card-{name}.svg")


def bengali_width(s, size):
    f = font("Noto Sans Bengali")
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap[ord(c)]][0] for c in s if ord(c) in cmap) / upm * size * 0.92


def network_visual(svg, inner):
    """ShareDeal: one farm at the centre, households around it in rings."""
    ix, iy, iw, ih, ir, clip, _ = inner
    cx, cy = ix + iw * 0.77, iy + ih * 0.5
    svg.add(f'<g clip-path="url(#{clip})">')
    import math
    rings = [(96, 6, 0.0), (168, 10, 0.3), (236, 14, 0.1)]
    for r, _, _ in rings:
        svg.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="rgba(255,255,255,0.07)" stroke-width="1.5" stroke-dasharray="2 8"/>')
    pts = []
    for r, n, off in rings:
        for k in range(n):
            a = 2 * math.pi * (k / n + off)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), r))
    for (x, y, r) in pts:
        svg.add(f'<path d="M{cx} {cy}L{x:.1f} {y:.1f}" stroke="rgba(52,211,153,{0.20 if r<150 else 0.10})" stroke-width="1.2"/>')
    for i, (x, y, r) in enumerate(pts):
        rr = 9 if r < 150 else (7 if r < 250 else 5.5)
        col = "#34D399" if i % 4 else "#FBBF24"
        svg.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr+6}" fill="{col}" opacity="0.10"/>')
        svg.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr}" fill="#0B0B0D" stroke="{col}" stroke-width="2"/>')
    for d in (0, 1.6, 3.2):
        svg.add(f'<circle cx="{cx}" cy="{cy}" r="40" stroke="#34D399" stroke-width="2" fill="none" opacity="0">'
                f'<animate attributeName="r" values="40;250" dur="4.8s" begin="{d}s" repeatCount="indefinite" calcMode="spline" keySplines="0.32 0.72 0 1"/>'
                f'<animate attributeName="opacity" values="0.5;0" dur="4.8s" begin="{d}s" repeatCount="indefinite"/></circle>')
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="58" fill="#34D399" opacity="0.12"/>')
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="40" fill="#F4F4F5"/>')
    # leaf glyph
    svg.add(f'<path d="M{cx-12} {cy+12}C{cx-12} {cy-6} {cx-2} {cy-14} {cx+14} {cy-14}C{cx+14} {cy+2} {cx+6} {cy+14} {cx-12} {cy+12}ZM{cx-12} {cy+12}L{cx+4} {cy-4}" stroke="#050505" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>')
    svg.add("</g>")


def build_cards():
    F = 1600
    build_card("sharedeal", F, "01", "Founder · Live in Bangladesh", "ShareDeal",
               "Neighbourhood group buying that connects Bangladeshi farmers directly with households. "
               "Customer app, rider app, seller portal and a multi-seller marketplace, all built and run by a small team.",
               ["Flutter", "Group buying", "Marketplace", "Logistics", "AWS"],
               "#10B981", "#F59E0B", height=600, visual=network_visual)
    rows = [
        [("gonok", 0.6, "02", "Fintech", "Gonok",
          "Offline-first accounting for Bangladeshi small businesses. Works without internet and syncs when it can.",
          ["Angular 21", "Express", "PouchDB", "CouchDB"], "#F59E0B", "#EF4444", "গণক"),
         ("openiga", 0.4, "03", "Identity", "OpenIGA",
          "Open-source identity governance. A self-hosted alternative to One Identity Manager.",
          ["Angular", "NestJS", "Postgres"], "#8B5CF6", "#3B82F6", None)],
        [("folio", 0.4, "04", "Wealth", "Folio",
          "Investment management with FIFO valuation, TWR and XIRR performance, and fee billing.",
          ["Angular 22", "Express 5", "Postgres"], "#3B82F6", "#06B6D4", None),
         ("pulse", 0.6, "05", "Infrastructure", "Pulse",
          "Multi-tenant notification delivery: email, push, SMS, in-app inbox and webhooks behind one API.",
          ["AWS serverless", "TypeScript", "Multi-tenant"], "#EC4899", "#8B5CF6", None)],
        [("garments", 0.5, "06", "Enterprise", "Garments ERP",
          "Multi-tenant ERP for Bangladesh's garment industry, covering production, inventory and payroll.",
          ["Angular 20", "NestJS 11", "Nx"], "#06B6D4", "#10B981", None),
         ("lattice", 0.5, "07", "Developer tools", "Lattice",
          "Schema-driven CRUD builder. Design tables in a UI and get real Postgres tables, forms and permissions.",
          ["TypeScript", "Postgres", "Formulas"], "#A3E635", "#10B981", None)],
        [("shikkha", 0.6, "08", "Education", "Shikkha",
          "School management for Bangladesh with NCTB grading, bKash and Nagad fees, and Bangla and English throughout.",
          ["Angular 20", "Spring Boot 3", "Postgres"], "#F97316", "#EAB308", None),
         ("kiln", 0.4, "09", "Design systems", "Kiln UI",
          "Angular and Flutter component libraries drawn from Bangladeshi visual heritage.",
          ["Angular", "Flutter", "56 widgets"], "#EF4444", "#F59E0B", None)],
    ]
    for row in rows:
        for (name, frac, idx, cat, title, desc, tags, a1, a2, bn) in row:
            build_card(name, int(F * frac), idx, cat, title, desc, tags, a1, a2, bn)


# ── stack panel ──────────────────────────────────────────────────────────
def build_stack():
    W, H = 1600, 560
    s = Svg(W, H)
    inner = bezel(s, 0, 0, W, H, r=44, pad=8)
    ix, iy, iw, ih, ir, clip, _ = inner
    s.add(f'<g clip-path="url(#{clip})">')
    glow(s, ix + 200, iy, 520, "#3B82F6", 0.16, (40, 20, 24))
    glow(s, ix + iw - 120, iy + ih, 520, "#8B5CF6", 0.16, (-40, -20, 26))
    s.add("</g>")
    grain(s, ix, iy, iw, ih, clip, 0.045)
    groups = [
        ("Frontend & mobile", "#60A5FA", ["Angular", "TypeScript", "React", "Next.js", "Flutter", "Dart", "Tailwind", "Ionic"]),
        ("Backend & data", "#34D399", ["Node.js", "NestJS", "Express", "Spring Boot", "Laravel", "PostgreSQL", "MongoDB", "Redis", "Kafka"]),
        ("Cloud & delivery", "#FBBF24", ["AWS", "Docker", "Cloudflare", "Firebase", "Nx", "GitHub Actions", "Terraform"]),
        ("Identity & security", "#A78BFA", ["SailPoint", "One Identity", "OAuth 2.0", "OIDC", "SAML", "IGA", "GDPR"]),
    ]
    p = 56
    colw = (iw - 2 * p) / 4
    for i, (label, col, items) in enumerate(groups):
        x = ix + p + i * colw
        if i:
            s.add(f'<path d="M{x-28:.1f} {iy+p}V{iy+ih-p}" stroke="rgba(255,255,255,0.06)" stroke-width="1.5"/>')
        s.add(f'<circle cx="{x+5}" cy="{iy+p+12}" r="5" fill="{col}"/>')
        s.text(x + 22, iy + p + 18, label.upper(), 16, 500, "#8E8E97", "Geist Mono", 2.4)
        for j, it in enumerate(items):
            yy = iy + p + 78 + j * 44
            s.text(x, yy, it, 27, 400 if j else 500, TEXT if j < 3 else "#C4C4CC", "Geist", -0.4)
    bezel_highlight(s, inner)
    s.save("stack.svg")


# ── handbook tiles ───────────────────────────────────────────────────────
HANDBOOKS = [
    ("llm-engineering-handbook", "AI", "LLM Engineering", "#8B5CF6"),
    ("mlops-for-developers", "AI", "MLOps for Developers", "#8B5CF6"),
    ("learn-claude", "AI", "Learn Claude", "#8B5CF6"),
    ("aws-for-devs", "Cloud", "AWS for Devs", "#F59E0B"),
    ("cloudflare-for-devs", "Cloud", "Cloudflare for Devs", "#F59E0B"),
    ("networking-for-developers", "Systems", "Networking for Devs", "#3B82F6"),
    ("databases-compared", "Systems", "Databases Compared", "#3B82F6"),
    ("go-developer-path", "Language", "Go Developer Path", "#06B6D4"),
    ("iam-architect-roadmap", "Identity", "IAM Architect Roadmap", "#10B981"),
    ("gdpr-engineer-playbook", "Compliance", "GDPR Engineer Playbook", "#10B981"),
    ("senior-interview-prep", "Career", "Senior Interview Prep", "#EC4899"),
    ("scrum-zero-to-master", "Career", "Scrum: Zero to Master", "#EC4899"),
]


def build_handbooks():
    W, H = 533, 220
    for repo, cat, title, col in HANDBOOKS:
        s = Svg(W, H)
        inner = bezel(s, GUT, GUT, W - 2 * GUT, H - 2 * GUT, r=34, pad=7)
        ix, iy, iw, ih, ir, clip, _ = inner
        s.add(f'<g clip-path="url(#{clip})">')
        glow(s, ix + iw, iy, 260, col, 0.22)
        s.add("</g>")
        p = 32
        s.add(f'<circle cx="{ix+p+4}" cy="{iy+p+10}" r="4.5" fill="{col}"/>')
        s.text(ix + p + 18, iy + p + 16, cat.upper(), 15, 500, "#8E8E97", "Geist Mono", 2.4)
        arrow_button(s, ix + iw - p - 18, iy + p + 10, 22)
        fs = 32
        while measure(title, fs, "Geist", 500, -0.9) > iw - 2 * p and fs > 24:
            fs -= 1
        s.text(ix + p, iy + ih - p - 4, title, fs, 500, TEXT, "Geist", -0.9)
        bezel_highlight(s, inner)
        s.save(f"book-{repo}.svg")


# ── live stats ───────────────────────────────────────────────────────────
def gql(query, variables):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-build"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(json.dumps(data["errors"]))
    return data["data"]


def fetch_stats():
    q = """query($login:String!,$after:String){user(login:$login){
      followers{totalCount}
      contributionsCollection{contributionCalendar{totalContributions
        weeks{contributionDays{contributionCount date weekday}}}}
      repositories(first:100,after:$after,ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC){
        totalCount pageInfo{hasNextPage endCursor}
        nodes{stargazerCount languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}}}"""
    after, stars, langs, first = None, 0, {}, None
    while True:
        d = gql(q, {"login": USER, "after": after})["user"]
        first = first or d
        for n in d["repositories"]["nodes"]:
            stars += n["stargazerCount"]
            # Weight by repository, not bytes: each repo contributes one unit split
            # across its languages, so vendored code in old repos can't dominate.
            edges = [e for e in n["languages"]["edges"] if e["node"]["name"] not in SKIP_LANGS]
            tot = sum(e["size"] for e in edges)
            for e in edges:
                nm = e["node"]["name"]
                langs.setdefault(nm, [0, e["node"]["color"] or "#888"])
                langs[nm][0] += e["size"] / tot
        pi = d["repositories"]["pageInfo"]
        if not pi["hasNextPage"]:
            break
        after = pi["endCursor"]
    cal = first["contributionsCollection"]["contributionCalendar"]
    return {
        "followers": first["followers"]["totalCount"],
        "repos": first["repositories"]["totalCount"],
        "stars": stars,
        "contrib": cal["totalContributions"],
        "weeks": cal["weeks"],
        "langs": langs,
    }


SKIP_LANGS = {"HTML", "CSS", "SCSS", "Less", "Makefile", "Dockerfile", "Shell", "Procfile",
              "Batchfile", "PowerShell", "Hack", "Blade", "Handlebars", "EJS", "Twig", "Smarty", "Tcl", "Jupyter Notebook", "Cython"}


def build_stats(st):
    W, H = 1600, 760
    s = Svg(W, H)
    inner = bezel(s, 0, 0, W, H, r=44, pad=8)
    ix, iy, iw, ih, ir, clip, _ = inner
    s.add(f'<g clip-path="url(#{clip})">')
    glow(s, ix + iw - 100, iy + 40, 560, "#10B981", 0.18, (-40, 30, 22))
    glow(s, ix + 100, iy + ih, 520, "#3B82F6", 0.14, (40, -20, 26))
    s.add("</g>")
    grain(s, ix, iy, iw, ih, clip, 0.045)
    p = 56
    x0, y0 = ix + p, iy + p
    s.add(f'<circle cx="{x0+5}" cy="{y0+12}" r="5" fill="#34D399" style="animation:blink 2.4s {EASE} infinite"/>')
    s.text(x0 + 22, y0 + 18, "LIVE  /  UPDATED DAILY", 16, 500, "#8E8E97", "Geist Mono", 2.6)
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y")
    s.text(ix + iw - p, y0 + 18, f"AS OF {today.upper()}", 16, 500, "#6B6B73", "Geist Mono", 2.6, "end")

    nums = [(f"{st['contrib']:,}", "Contributions, past year"),
            (f"{st['repos']}", "Public repositories"),
            (f"{st['stars']}", "Stars earned"),
            (f"{st['followers']}", "Followers")]
    cw = (iw - 2 * p) / 4
    for i, (n, label) in enumerate(nums):
        x = x0 + i * cw
        if i:
            s.add(f'<path d="M{x-28:.1f} {y0+70}V{y0+190}" stroke="rgba(255,255,255,0.07)" stroke-width="1.5"/>')
        s.text(x, y0 + 152, n, 76, 500, TEXT, "Geist", -3.2)
        s.text(x, y0 + 192, label, 22, 400, MUTED, "Geist", -0.2)

    # heatmap, full width
    weeks = st["weeks"][-53:]
    gap = 5.0
    cell = ((iw - 2 * p) - gap * (len(weeks) - 1)) / len(weeks)
    hx, hy = x0, y0 + 268
    days = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    nz = sorted(c for c in days if c)
    def q(f):
        return nz[min(len(nz) - 1, int(len(nz) * f))] if nz else 1
    cuts = [q(.25), q(.5), q(.8)]
    shades = ["rgba(255,255,255,0.045)", "#053B2C", "#04694A", "#10B981", "#6EE7B7"]
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            c = d["contributionCount"]
            lvl = 0 if c == 0 else 1 + sum(c > k for k in cuts)
            x = hx + wi * (cell + gap)
            y = hy + d["weekday"] * (cell + gap)
            s.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="{cell*0.26:.1f}" fill="{shades[lvl]}"/>')
    seen = None
    for wi, w in enumerate(weeks):
        m = w["contributionDays"][0]["date"][5:7]
        if m != seen:
            if seen is not None and wi < len(weeks) - 2:
                name = datetime.date(2000, int(m), 1).strftime("%b").upper()
                s.text(hx + wi * (cell + gap), hy - 18, name, 15, 500, DIM, "Geist Mono", 2)
            seen = m
    ly = hy + 7 * (cell + gap) + 30
    # legend for heatmap, right aligned
    lgx = ix + iw - p - 5 * (16 + 6) - 4
    s.text(lgx - 14, ly + 13, "LESS", 13, 500, DIM, "Geist Mono", 2, "end")
    for k, sh in enumerate(shades):
        s.add(f'<rect x="{lgx + k*22:.1f}" y="{ly}" width="16" height="16" rx="4" fill="{sh}"/>')
    s.text(lgx + 5 * 22 + 10, ly + 13, "MORE", 13, 500, DIM, "Geist Mono", 2)

    # languages row
    ranked = sorted(((v[0], k, v[1]) for k, v in st["langs"].items() if k not in SKIP_LANGS), reverse=True)
    top = ranked[:6]
    shown = sum(t[0] for t in top) or 1
    by = ly + 62
    s.add(f'<path d="M{x0} {by-22}H{ix+iw-p}" stroke="rgba(255,255,255,0.07)" stroke-width="1.5"/>')
    s.text(x0, by + 24, "LANGUAGES BY REPO", 15, 500, DIM, "Geist Mono", 2.4)
    bx = x0 + 230
    bw = ix + iw - p - bx
    cid = s.uid("bar")
    s.defs.append(f'<clipPath id="{cid}"><rect x="{bx}" y="{by+8}" width="{bw:.1f}" height="14" rx="7"/></clipPath>')
    s.add(f'<g clip-path="url(#{cid})">')
    cx = bx
    for size, nm, col in top:
        seg = bw * size / shown
        s.add(f'<rect x="{cx:.1f}" y="{by+8}" width="{max(seg-3,1):.1f}" height="14" fill="{col}"/>')
        cx += seg
    s.add("</g>")
    lx = bx
    for size, nm, col in top:
        s.add(f'<circle cx="{lx+6}" cy="{by+58}" r="6" fill="{col}"/>')
        s.text(lx + 22, by + 65, nm, 21, 500, TEXT, "Geist", -0.2)
        lx += 22 + measure(nm, 21, "Geist", 500, -0.2) + 10
        pct = f"{100*size/shown:.0f}%"
        s.text(lx, by + 65, pct, 18, 400, MUTED, "Geist Mono", 0)
        lx += measure(pct, 18, "Geist Mono") + 40
    bezel_highlight(s, inner)
    s.save("stats.svg")


# ── footer ───────────────────────────────────────────────────────────────
def build_footer():
    W, H = 1600, 470
    s = Svg(W, H)
    inner = bezel(s, 0, 0, W, H, r=48, pad=10)
    ix, iy, iw, ih, ir, clip, _ = inner
    s.add(f'<g clip-path="url(#{clip})">')
    glow(s, W / 2, ih + 120, 700, "#7C3AED", 0.30, (0, -30, 20))
    glow(s, W * 0.2, 0, 420, "#10B981", 0.16, (40, 20, 24))
    glow(s, W * 0.85, 40, 420, "#3B82F6", 0.16, (-40, 20, 22))
    s.add("</g>")
    grid(s, ix, iy, iw, ih, clip, 64, W / 2, ih)
    grain(s, ix, iy, iw, ih, clip, 0.05)
    lab = "Get in touch"
    w = measure(lab.upper(), 17, "Geist Mono", 500, 2.6) + 60
    s.add('<g class="up">')
    eyebrow(s, W / 2 - w / 2, 92, lab, dot="#34D399")
    s.add("</g>")
    s.add('<g class="up" style="animation-delay:.15s">')
    s.text(W / 2, 252, "Let's build something that lasts.", 92, 500, TEXT, "Geist", -4, "middle")
    s.add("</g>")
    s.add('<g class="up" style="animation-delay:.3s">')
    s.text(W / 2, 326, "Architecture and identity work, product builds, open source and startup conversations.", 28, 400, MUTED, "Geist", -0.3, "middle")
    s.text(W / 2, 370, "LinkedIn is the fastest way to reach me.", 28, 400, MUTED, "Geist", -0.3, "middle")
    s.add("</g>")
    bezel_highlight(s, inner)
    s.save("footer.svg")


def main():
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[1:])
    if not only or "static" in only:
        print("static art")
        build_hero()
        build_button("portfolio", "omerarafat.com", primary=True)
        build_button("linkedin", "LinkedIn")
        build_button("email", "Email")
        build_button("x", "X / Twitter")
        build_header("work", "01", "Selected work", "Things I've built", "Products, platforms and tools")
        build_header("stack", "02", "Toolkit", "What I build with", "Eight years across the stack")
        build_header("books", "03", "Writing", "Handbooks I've written", "Free, long-form, for working developers")
        build_header("pulse", "04", "Activity", "On GitHub lately", "Refreshed every day")
        build_cards()
        build_stack()
        build_handbooks()
        build_footer()
    if not only or "stats" in only:
        print("live stats")
        build_stats(fetch_stats())


if __name__ == "__main__":
    main()
