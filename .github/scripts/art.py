"""README art for pushback, in the "sunset circuit" theme. Standard library only.

Run from the repo root:  python .github/scripts/art.py   ->  writes assets/*.svg
The numbers in rates() come from the author's own run (README "Results").
"""
import os
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets")

BG, CARD, EDGE = "#0A0A14", "#12121F", "#26263D"
TEXT, MUTED = "#F6F4FF", "#A3A1BE"
CORAL, AMBER, LIME, PINK, BLUE = "#FF5C39", "#FFB224", "#A3F547", "#FF3D9A", "#5B8CFF"
VIOLET = "#B794FF"
SANS = "'Segoe UI', Inter, -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


def x(s):
    return escape(str(s))


CSS = f"""<style>
.sans{{font-family:{SANS};}} .mono{{font-family:{MONO};letter-spacing:1.2px;}}
.blob{{animation:float 14s ease-in-out infinite alternate;}}
.b2{{animation-duration:18s;animation-direction:alternate-reverse;}} .b3{{animation-duration:22s;}}
@keyframes float{{from{{transform:translate(0,0) scale(1);}} to{{transform:translate(60px,-40px) scale(1.15);}}}}
.pulse{{animation:pulse 2s ease-in-out infinite;}}
@keyframes pulse{{0%,100%{{opacity:1;}} 50%{{opacity:.25;}}}}
.rot{{opacity:0;animation:rot 12s infinite both;}}
@keyframes rot{{0%{{opacity:0;transform:translateY(16px);}} 4%,29%{{opacity:1;transform:translateY(0);}} 33%,100%{{opacity:0;transform:translateY(-16px);}}}}
.move{{animation:move 2.6s linear infinite;}}
@keyframes move{{from{{transform:translateX(0);opacity:0;}} 15%{{opacity:1;}} 85%{{opacity:1;}} to{{transform:translateX(var(--dx,120px));opacity:0;}}}}
.shine{{animation:shine 6s linear infinite;}}
@keyframes shine{{from{{transform:translateX(-400px);}} to{{transform:translateX(1400px);}}}}
.enter{{animation:enter .9s cubic-bezier(.2,.8,.2,1) both;}}
@keyframes enter{{from{{transform:translateY(-14px);opacity:0;}} to{{transform:translateY(0);opacity:1;}}}}
.growx{{animation:growx 1.4s cubic-bezier(.2,.8,.2,1) both;transform-box:fill-box;transform-origin:left;}}
@keyframes growx{{from{{transform:scaleX(0);}} to{{transform:scaleX(1);}}}}
.type{{animation:type 7s steps(1) infinite both;}}
@keyframes type{{0%{{opacity:0;}} 18%,100%{{opacity:1;}}}}
.t2{{animation-name:type2;}} @keyframes type2{{0%{{opacity:0;}} 42%,100%{{opacity:1;}}}}
.t3{{animation-name:type3;}} @keyframes type3{{0%{{opacity:0;}} 66%,100%{{opacity:1;}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;}} .rot{{opacity:0;}} .r0{{opacity:1;}}}}
</style>"""


def defs(uid):
    return f"""<defs>
<linearGradient id="sun{uid}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{AMBER}"/><stop offset=".5" stop-color="{CORAL}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>
<linearGradient id="edge{uid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{AMBER}" stop-opacity=".9"/><stop offset=".5" stop-color="{PINK}" stop-opacity=".35"/><stop offset="1" stop-color="{BLUE}" stop-opacity=".8"/></linearGradient>
<filter id="blur{uid}" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="46"/></filter>
<filter id="glow{uid}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<pattern id="dots{uid}" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.1" fill="{EDGE}"/></pattern>
</defs>"""


def svg(w, h, title, body, uid="", blobs=True, css=True):
    bl = ""
    if blobs:
        bl = (f'<g filter="url(#blur{uid})" opacity=".5">'
              f'<circle class="blob" cx="{w*.12:.0f}" cy="{h*.2:.0f}" r="{min(w,h)*.32:.0f}" fill="{CORAL}"/>'
              f'<circle class="blob b2" cx="{w*.8:.0f}" cy="{h*.85:.0f}" r="{min(w,h)*.3:.0f}" fill="{BLUE}"/>'
              f'<circle class="blob b3" cx="{w*.55:.0f}" cy="{h*.1:.0f}" r="{min(w,h)*.22:.0f}" fill="{PINK}"/></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{x(title)}">'
            f'<title>{x(title)}</title>{CSS if css else ""}{defs(uid)}'
            f'<clipPath id="clip{uid}"><rect width="{w}" height="{h}" rx="20"/></clipPath>'
            f'<g clip-path="url(#clip{uid})"><rect width="{w}" height="{h}" fill="{BG}"/>{bl}'
            f'<rect width="{w}" height="{h}" fill="url(#dots{uid})" opacity=".6"/>{body}</g>'
            f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="19" fill="none" stroke="url(#edge{uid})" stroke-width="1.5"/></svg>')


def chip(px, py, label, color):
    w = len(label) * 7.4 + 26
    return (f'<rect x="{px}" y="{py}" width="{w:.0f}" height="26" rx="13" fill="{CARD}" stroke="{color}" stroke-opacity=".55"/>'
            f'<text x="{px + 13}" y="{py + 17.5}" class="mono" font-size="11" fill="{color}">{x(label)}</text>'), w


def chips(px, py, items, gap=10):
    out, cx = [], px
    for label, col in items:
        c, w = chip(cx, py, label, col)
        out.append(c)
        cx += w + gap
    return "".join(out)


def bubble(bx, by, w, who, lines, col, cls=""):
    h = 34 + 20 * len(lines)
    text = "".join(f'<text x="{bx + 18}" y="{by + 46 + i*20}" class="sans" font-size="15" fill="{TEXT}">{x(t)}</text>'
                   for i, t in enumerate(lines))
    return (f'<g class="{cls}"><rect x="{bx}" y="{by}" width="{w}" height="{h}" rx="14" fill="{CARD}" stroke="{col}" stroke-opacity=".6"/>'
            f'<text x="{bx + 18}" y="{by + 22}" class="mono" font-size="10" fill="{col}">{x(who)}</text>{text}</g>')


# ---------------------------------------------------------------- hero
def hero():
    W, H = 1200, 440
    lines = [("How often do you", "correct your coding agent?", CORAL),
             ("Which of your rules", "does it keep breaking?", PINK),
             ("Where does it need", "a second correction?", LIME)]
    rot = "".join(
        f'<text class="sans rot{" r0" if i == 0 else ""}" style="animation-delay:{i*4}s" x="64" y="238" font-size="30" font-weight="700" fill="{TEXT}">'
        f'{x(a)} <tspan fill="{c}">{x(b)}</tspan></text>' for i, (a, b, c) in enumerate(lines))
    convo = (bubble(720, 58, 420, "AGENT", ["Here's the post. It opens with context,", "then the result lands at the end."], BLUE, "type")
             + bubble(760, 158, 380, "YOU · PUSHBACK", ["no, the last line is the hook.", "put it first."], CORAL, "type t2")
             + bubble(720, 258, 420, "PUSHBACK RULES", ["Put the strongest line first.", "3 corrections · rule drafted"], LIME, "type t3"))
    body = f"""
<rect x="64" y="52" width="290" height="30" rx="15" fill="{CARD}" stroke="{LIME}" stroke-opacity=".6"/>
<circle class="pulse" cx="84" cy="67" r="5" fill="{LIME}" filter="url(#glow)"/>
<text x="98" y="71.5" class="mono" font-size="11" fill="{LIME}">OPEN SOURCE · PIP INSTALL PUSHBACK</text>
<text x="58" y="176" class="sans" font-size="104" font-weight="800" letter-spacing="-4" fill="url(#sun)" filter="url(#glow)">pushback</text>
{rot}
{chips(64, 282, [("CLAUDE CODE", CORAL), ("CORRECTION RATE", AMBER), ("CLAUDE.MD RULES", LIME)])}
{chips(64, 318, [("PREFERENCE PAIRS", PINK), ("HAND AUDIT", BLUE), ("RUNS LOCALLY", VIOLET)])}
<line x1="64" y1="372" x2="640" y2="372" stroke="{EDGE}"/>
<text x="64" y="402" class="mono" font-size="12" fill="{MUTED}">EXTRACT · LABEL · AUDIT · REPORT · RULES · EXPORT</text>
{convo}
<rect class="shine" x="0" y="0" width="120" height="{H}" fill="#fff" opacity=".035" transform="skewX(-20)"/>"""
    return svg(W, H, "pushback: measure how often you correct your AI coding agent, find the rules it keeps breaking, "
                     "and export your corrections as preference pairs.", body)


# ---------------------------------------------------------------- results
RATES = [("media", 114, 49, .430, .343, .522, PINK), ("writing", 429, 106, .247, .209, .290, CORAL),
         ("research", 188, 13, .069, .041, .115, AMBER), ("code", 340, 20, .059, .038, .089, LIME),
         ("meta", 297, 14, .047, .028, .078, BLUE), ("ops", 265, 12, .045, .026, .077, VIOLET)]


def rates():
    W, H = 1200, 520
    x0, x1 = 230, 800  # 0% .. 60%
    sc = lambda p: x0 + (x1 - x0) * p / .6
    rows = []
    for i, (task, n, k, r, lo, hi, col) in enumerate(RATES):
        y = 132 + i * 52
        rows.append(
            f'<text x="{x0 - 20}" y="{y + 19}" class="sans" font-size="18" font-weight="700" fill="{TEXT}" text-anchor="end">{task}</text>'
            f'<rect x="{x0}" y="{y}" width="{sc(.6) - x0:.0f}" height="28" rx="6" fill="{CARD}"/>'
            f'<rect class="growx" style="animation-delay:{i*.12:.2f}s" x="{x0}" y="{y}" width="{sc(r) - x0:.1f}" height="28" rx="6" fill="{col}" opacity=".9"/>'
            f'<line x1="{sc(lo):.1f}" y1="{y + 14}" x2="{sc(hi):.1f}" y2="{y + 14}" stroke="{TEXT}" stroke-width="2" opacity=".85"/>'
            f'<line x1="{sc(lo):.1f}" y1="{y + 7}" x2="{sc(lo):.1f}" y2="{y + 21}" stroke="{TEXT}" stroke-width="2" opacity=".85"/>'
            f'<line x1="{sc(hi):.1f}" y1="{y + 7}" x2="{sc(hi):.1f}" y2="{y + 21}" stroke="{TEXT}" stroke-width="2" opacity=".85"/>'
            f'<text x="{sc(hi) + 12:.1f}" y="{y + 19}" class="mono" font-size="14" fill="{col}">{r:.1%}</text>'
            f'<text x="{sc(hi) + 80:.1f}" y="{y + 19}" class="mono" font-size="11" fill="{MUTED}">{k}/{n}</text>')
    ticks = "".join(
        f'<line x1="{sc(p):.0f}" y1="122" x2="{sc(p):.0f}" y2="{132 + 6*52 - 14}" stroke="{EDGE}" stroke-dasharray="3 5"/>'
        f'<text x="{sc(p):.0f}" y="{132 + 6*52 + 6}" class="mono" font-size="11" fill="{MUTED}" text-anchor="middle">{p:.0%}</text>'
        for p in (0, .2, .4, .6))

    def stat(sx, sy, big, col, a, b):
        return (f'<rect x="{sx}" y="{sy}" width="300" height="118" rx="16" fill="{CARD}" stroke="{col}" stroke-opacity=".55"/>'
                f'<text x="{sx + 24}" y="{sy + 58}" class="sans" font-size="46" font-weight="800" fill="{col}">{x(big)}</text>'
                f'<text x="{sx + 24}" y="{sy + 84}" class="sans" font-size="14" fill="{TEXT}">{x(a)}</text>'
                f'<text x="{sx + 24}" y="{sy + 104}" class="sans" font-size="14" fill="{MUTED}">{x(b)}</text>')

    body = f"""
<text x="64" y="62" class="sans" font-size="28" font-weight="800" fill="{TEXT}">Correction rate by task</text>
<text x="64" y="90" class="mono" font-size="12" fill="{MUTED}">1,633 MESSAGES · ONE DEVELOPER · BARS = RATE · WHISKERS = 95% CI</text>
{ticks}{''.join(rows)}
{stat(860, 118, "1 in 3", CORAL, "corrections needed a second one:", "70 of 201 fixes got corrected again")}
{stat(860, 256, "3 more", LIME, "times a written rule got broken:", "images must not look AI-generated")}
<text x="64" y="{H - 30}" class="sans" font-size="14" fill="{MUTED}">These rates describe a workflow, not a model: the code work ran through skills, references, memory, plans and CI first. Writing didn't.</text>"""
    return svg(W, H, "Correction rate by task on the author's 1,633 messages: media 43.0%, writing 24.7%, research 6.9%, "
                     "code 5.9%, meta 4.7%, ops 4.5%. One in three corrections needed a second correction. One written rule was broken 3 more times.", body)


# ---------------------------------------------------------------- pipeline
def pipeline():
    W, H = 1200, 300
    steps = [("EXTRACT", "your messages from", "Claude Code transcripts", CORAL),
             ("LABEL", "task + correction", "per message, by Claude", AMBER),
             ("AUDIT", "hand-check a sample", "to bound the error", LIME)]
    outs = [("REPORT", "rate per task, with CIs", PINK), ("RULES", "CLAUDE.md rules that stick", BLUE),
            ("EXPORT", "prompt / chosen / rejected", VIOLET)]
    body = [f'<text x="64" y="54" class="sans" font-size="24" font-weight="800" fill="{TEXT}">How it works</text>']
    for i, (name, a, b, col) in enumerate(steps):
        bx = 64 + i * 250
        body.append(
            f'<g class="enter" style="animation-delay:{i*.15:.2f}s"><rect x="{bx}" y="90" width="210" height="150" rx="16" fill="{CARD}" stroke="{col}" stroke-opacity=".6"/>'
            f'<text x="{bx + 20}" y="124" class="mono" font-size="13" font-weight="700" fill="{col}">0{i+1} · {name}</text>'
            f'<text x="{bx + 20}" y="170" class="sans" font-size="16" fill="{TEXT}">{x(a)}</text>'
            f'<text x="{bx + 20}" y="194" class="sans" font-size="16" fill="{MUTED}">{x(b)}</text></g>')
        ax = bx + 214
        body.append(f'<line x1="{ax}" y1="165" x2="{ax + 32}" y2="165" stroke="{EDGE}" stroke-width="2"/>'
                    f'<circle class="move" style="--dx:32px;animation-delay:{i*.4:.1f}s" cx="{ax}" cy="165" r="4" fill="{col}" filter="url(#glow)"/>')
    for i, (name, a, col) in enumerate(outs):
        oy = 78 + i * 62
        body.append(
            f'<g class="enter" style="animation-delay:{.5 + i*.15:.2f}s"><rect x="820" y="{oy}" width="316" height="50" rx="14" fill="{CARD}" stroke="{col}" stroke-opacity=".6"/>'
            f'<text x="840" y="{oy + 31}" class="mono" font-size="13" font-weight="700" fill="{col}">{name}</text>'
            f'<text x="930" y="{oy + 31}" class="sans" font-size="15" fill="{TEXT}">{x(a)}</text></g>')
        body.append(f'<path d="M 778 165 C 800 165, 800 {oy + 25}, 820 {oy + 25}" fill="none" stroke="{EDGE}" stroke-width="2"/>')
    return svg(W, H, "How pushback works: extract your messages from Claude Code transcripts, label them, audit a sample, "
                     "then report correction rates, draft CLAUDE.md rules, or export preference pairs.", "".join(body))


# ---------------------------------------------------------------- social preview
def social():
    W, H = 1280, 640
    body = f"""
<text x="80" y="250" class="sans" font-size="150" font-weight="800" letter-spacing="-6" fill="url(#sun)" filter="url(#glow)">pushback</text>
<text x="84" y="330" class="sans" font-size="40" font-weight="700" fill="{TEXT}">How often do you <tspan fill="{CORAL}">correct your coding agent?</tspan></text>
<text x="84" y="390" class="sans" font-size="28" fill="{MUTED}">Correction rates · CLAUDE.md rules · preference pairs</text>
{chips(84, 460, [("PIP INSTALL PUSHBACK", LIME), ("CLAUDE CODE", CORAL), ("OPEN SOURCE · MIT", BLUE)], 14)}
<text x="84" y="570" class="mono" font-size="18" fill="{MUTED}">github.com/intikhab49/pushback</text>"""
    return svg(W, H, "pushback: how often do you correct your coding agent?", body)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in [("hero", hero), ("rates", rates), ("pipeline", pipeline), ("social", social)]:
        path = os.path.join(OUT, f"{name}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(fn())
        print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
