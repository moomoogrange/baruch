#!/usr/bin/env python3
"""seal.py — 서류에 얹을 도장 그림 만들기 (바룩 seal-maker 스킬)

이름이나 단체 이름을 받아 도장 그림(SVG, 바탕이 투명한 PNG)을 만든다.
파이썬 3만 있으면 SVG가 나온다. PNG와 견본 모음은 크롬이나 엣지가 있어야 한다.

  seal.py corp "주식회사 한빛"                 법인·단체 도장 견본 모음 (번호가 붙은 견본.png)
  seal.py corp "주식회사 한빛" --pick 3        3번 모양으로 도장 만들기 (.svg .png)
  seal.py corp "사단법인 푸른숲" --center 이사장   가운데 글자를 바꾼다 (기본: 대표이사, 代表理事)
  seal.py name "홍길동"                        개인 도장 견본 모음
  seal.py name "홍길동" --pick 4 --out 첨부     4번 모양을 첨부 폴더에 만든다
  seal.py corp "주식회사 한빛" --font 전서체.ttf  가진 글꼴 파일로 그린 모양을 앞에 더한다

글꼴은 컴퓨터에 깔린 명조·고딕을 쓴다. --font 로 준 글꼴 파일은 SVG 안에 넣는다.
만든 그림은 내 컴퓨터에만 남고 밖으로 보내지 않는다.
"""
import argparse
import base64
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

INK = "#e60012"
S = 600  # 도장 한 개의 그림 크기
SERIF = "'Nanum Myeongjo','NanumMyeongjo','AppleMyungjo','Batang','Noto Serif CJK KR','Noto Serif KR',serif"
SANS = "'Apple SD Gothic Neo','Malgun Gothic','Nanum Gothic','NanumGothic','Noto Sans CJK KR','Noto Sans KR',sans-serif"
USER = "'SealUser'," + SERIF
FONTS = {"명조": (SERIF, 800), "고딕": (SANS, 800), "가진 글꼴": (USER, 400)}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def is_han(ch):
    return "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"


def glyph(ch, x, y, size, font, rot=0, fill=INK, fatten=0):
    family, weight = FONTS[font]
    turn = f" rotate({rot:.2f})" if rot else ""
    thick = f' stroke="{fill}" stroke-width="{size * fatten:.1f}" stroke-linejoin="round"' if fatten else ""
    return (f'<text transform="translate({x:.2f} {y:.2f}){turn}" font-family="{family}" font-weight="{weight}" '
            f'font-size="{size:.1f}" text-anchor="middle" dominant-baseline="central" fill="{fill}"{thick}>{esc(ch)}</text>')


def chunk(seq, parts):
    per = math.ceil(len(seq) / parts)
    return [seq[i:i + per] for i in range(0, len(seq), per)]


def block(chars, cx, cy, w, h, font, vertical=False, fill=INK):
    """글자 묶음을 네모 칸 안에 놓는다. 한자는 오른쪽 줄부터 세로로, 한글·영문은 가로로."""
    n = len(chars)
    if not n:
        return ""
    out = []
    if vertical and n <= 4:
        ch = h / n
        size = min(w, ch) * 0.98
        return "".join(glyph(c, cx, cy - h / 2 + ch * (i + 0.5), size, font, fill=fill) for i, c in enumerate(chars))
    lines = 1 if n <= 2 else 2 if n <= 10 else 3
    groups = chunk(chars, lines)
    if all(is_han(c) for c in chars):
        cw = w / len(groups)
        for i, col in enumerate(groups):
            ch = h / len(col)
            x = cx + w / 2 - cw * (i + 0.5)
            out += [glyph(c, x, cy - h / 2 + ch * (j + 0.5), min(cw, ch) * 0.98, font, fill=fill) for j, c in enumerate(col)]
    else:
        rh = h / len(groups)
        for i, row in enumerate(groups):
            cw = w / len(row)
            y = cy - h / 2 + rh * (i + 0.5)
            out += [glyph(c, cx - w / 2 + cw * (j + 0.5), y, min(cw, rh) * 0.98, font, fill=fill) for j, c in enumerate(row)]
    return "".join(out)


def with_in(chars):
    """세 글자 이름처럼 칸이 비면 끝에 '인'을 붙여 채운다."""
    if len(chars) > 1 and len(chars) % 2 == 1:
        return chars + ["印" if is_han(chars[0]) else "인"]
    return chars


def star(cx, cy, r):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append(f"{cx + math.cos(a) * rr:.2f},{cy + math.sin(a) * rr:.2f}")
    return f'<polygon points="{" ".join(pts)}" fill="{INK}"/>'


def corp_seal(chars, ring_font, center, center_font, marker):
    """둘레에 단체 이름, 가운데에 직함. 이름은 맨 위 표시 오른쪽부터 시계 방향으로 돈다."""
    c, R = S / 2, 284
    r = R * 0.56
    mid, band = (R + r) / 2, R - r
    out = [f'<circle cx="{c}" cy="{c}" r="{R}" fill="none" stroke="{INK}" stroke-width="9"/>',
           f'<circle cx="{c}" cy="{c}" r="{r:.1f}" fill="none" stroke="{INK}" stroke-width="7"/>']
    out.append(star(c, c - mid, band * 0.24) if marker == "별"
               else f'<circle cx="{c}" cy="{c - mid:.1f}" r="{band * 0.19:.1f}" fill="{INK}"/>')
    step = 2 * math.pi / (len(chars) + 1)
    size = min(band * 0.6, mid * step * 0.92)
    for i, ch in enumerate(chars):
        a = -math.pi / 2 + step * (i + 1)
        out.append(glyph(ch, c + math.cos(a) * mid, c + math.sin(a) * mid, size, ring_font, rot=math.degrees(a) + 90))
    g = list(center)
    if len(g) == 4:
        cell = r * 0.8
        order = [g[2], g[0], g[3], g[1]] if all(is_han(x) for x in g) else g
        for i, ch in enumerate(order):
            out.append(glyph(ch, c + (0.5 if i % 2 else -0.5) * cell, c + (-0.5 if i < 2 else 0.5) * cell, cell * 0.98, center_font,
                             fatten=0.035 if center_font == "명조" else 0))
    else:
        side = r * 1.3
        out.append(block(g, c, c, side, side if len(g) > 2 else side * 0.6, center_font))
    return "".join(out)


def oval_seal(chars, font):
    rx, ry = 150, 215
    one = len(chars) == 1
    return (f'<ellipse cx="{S / 2}" cy="{S / 2}" rx="{rx}" ry="{ry}" fill="none" stroke="{INK}" stroke-width="10"/>'
            + block(chars, S / 2, S / 2, 170 if one else 150, 190 if one else 310, font, vertical=True))


def round_seal(chars, font):
    return (f'<circle cx="{S / 2}" cy="{S / 2}" r="240" fill="none" stroke="{INK}" stroke-width="14"/>'
            + block(chars, S / 2, S / 2, 310, 310, font))


def square_seal(chars, font, double=False):
    side, o = 440, 80
    out = f'<rect x="{o}" y="{o}" width="{side}" height="{side}" fill="none" stroke="{INK}" stroke-width="{10 if double else 14}"/>'
    if double:
        out += f'<rect x="{o + 22}" y="{o + 22}" width="{side - 44}" height="{side - 44}" fill="none" stroke="{INK}" stroke-width="4"/>'
    inner = 340 if double else 370
    return out + block(chars, S / 2, S / 2, inner, inner, font)


def corp_variants(chars, centers, has_user_font):
    rings = (["가진 글꼴"] if has_user_font else []) + ["명조", "고딕"]
    out = []
    for ring in rings:
        for center in centers:
            center_font = "명조" if all(is_han(x) for x in center) else "고딕"
            for marker in ("점", "별"):
                out.append((f"둘레 {ring} · 가운데 {center} · {marker}",
                            corp_seal(chars, ring, center, center_font, marker)))
    return out


def name_variants(chars, has_user_font):
    full = chars if len(chars) <= 4 else with_in(chars)
    padded = with_in(chars)
    out = []
    if has_user_font:
        out += [("타원 · 가진 글꼴", oval_seal(full, "가진 글꼴")),
                ("원 · 가진 글꼴", round_seal(padded, "가진 글꼴")),
                ("네모 · 가진 글꼴", square_seal(padded, "가진 글꼴"))]
    out += [("타원 · 첫 글자 · 명조", oval_seal(chars[:1], "명조")),
            ("타원 · 명조", oval_seal(full, "명조")),
            ("타원 · 고딕", oval_seal(full, "고딕")),
            ("원 · 명조", round_seal(padded, "명조")),
            ("네모 · 고딕", square_seal(padded, "고딕")),
            ("네모 · 명조", square_seal(padded, "명조")),
            ("네모 겹테 · 고딕", square_seal(padded, "고딕", double=True))]
    return out


def font_css(path):
    if not path:
        return ""
    p = Path(path).expanduser()
    if not p.is_file():
        sys.exit(f"글꼴 파일을 찾지 못했습니다: {p}")
    kind = {".ttf": "truetype", ".otf": "opentype", ".woff": "woff", ".woff2": "woff2"}.get(p.suffix.lower())
    if not kind:
        sys.exit("글꼴 파일은 .ttf .otf .woff .woff2 만 됩니다.")
    data = base64.b64encode(p.read_bytes()).decode()
    return f"<style>@font-face{{font-family:'SealUser';src:url(data:font/{kind};base64,{data}) format('{kind}')}}</style>"


def svg_doc(body, w, h, css=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">{css}{body}</svg>')


def sheet(variants, css, title):
    """번호를 붙인 견본 모음 한 장."""
    cols = 4
    rows = math.ceil(len(variants) / cols)
    cell, pad, head = 300, 20, 70
    w, h = cols * cell + pad * 2, rows * (cell + 44) + head + pad
    body = [f'<rect width="{w}" height="{h}" fill="#fff"/>',
            f'<text x="{pad}" y="44" font-family="{SANS}" font-size="26" font-weight="700" fill="#111">{esc(title)}</text>']
    for i, (label, inner) in enumerate(variants):
        x, y = pad + (i % cols) * cell, head + (i // cols) * (cell + 44)
        body.append(f'<rect x="{x + 6}" y="{y}" width="{cell - 12}" height="{cell - 12}" rx="8" fill="#eeedf2"/>')
        body.append(f'<g transform="translate({x + 26} {y + 20}) scale({(cell - 52) / S:.4f})">{inner}</g>')
        body.append(f'<text x="{x + 6}" y="{y + cell + 12}" font-family="{SANS}" font-size="16" fill="#111">'
                    f'<tspan font-weight="700">{i + 1}번</tspan> {esc(label)}</text>')
    return svg_doc("".join(body), w, h, css), w, h


def find_browser():
    paths = (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    )
    names = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser")
    found = [p for p in paths if Path(p).exists()] + [w for w in map(shutil.which, names) if w]
    return found[0] if found else None


def to_png(svg, png, w, h, transparent):
    """SVG를 크롬으로 PNG로 바꾼다. 도장은 바탕을 투명하게 둔다."""
    browser = find_browser()
    if not browser:
        print("  크롬이나 엣지를 찾지 못해 PNG는 만들지 못했습니다. SVG를 브라우저로 열어 쓰세요.", file=sys.stderr)
        return False
    bg = "transparent" if transparent else "#fff"
    with tempfile.TemporaryDirectory() as td:
        html = Path(td) / "seal.html"
        html.write_text(f'<!doctype html><meta charset="utf-8"><style>html,body{{margin:0;background:{bg}}}'
                        f'svg{{display:block}}</style>{svg}', encoding="utf-8")
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={td}/profile",
               "--hide-scrollbars", f"--window-size={w},{h}", "--force-device-scale-factor=2",
               f"--screenshot={png.resolve()}"]
        if transparent:
            cmd.append("--default-background-color=00000000")
        try:
            subprocess.run(cmd + [html.as_uri()], capture_output=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"  {png.name}을 만들지 못했습니다 ({e}).", file=sys.stderr)
    return png.exists() and png.stat().st_size > 0


def main():
    ap = argparse.ArgumentParser(description="서류에 얹을 도장 그림 만들기")
    ap.add_argument("kind", choices=["corp", "name"], help="corp: 법인·단체 도장, name: 개인 도장")
    ap.add_argument("text", help="단체 이름 또는 사람 이름")
    ap.add_argument("--center", action="append", help="법인 도장 가운데 글자 (여러 번 줄 수 있다. 기본: 대표이사, 代表理事)")
    ap.add_argument("--font", help="도장 글자에 쓸 글꼴 파일 (.ttf .otf .woff .woff2)")
    ap.add_argument("--pick", type=int, help="견본 번호. 주면 그 모양 하나만 도장 파일로 만든다")
    ap.add_argument("--out", default=".", help="만들 폴더 (기본: 지금 폴더)")
    a = ap.parse_args()

    chars = [c for c in a.text if not c.isspace()]
    if not chars:
        sys.exit("이름이 비어 있습니다.")
    if a.kind == "corp" and len(chars) > 24:
        sys.exit("둘레에 넣기에는 이름이 깁니다(24자까지). 줄여 쓴 이름으로 다시 해 보세요.")
    css = font_css(a.font)
    if a.kind == "corp":
        variants = corp_variants(chars, a.center or ["대표이사", "代表理事"], bool(a.font))
        what = "법인도장"
    else:
        variants = name_variants(chars, bool(a.font))
        what = "도장"
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    stem = "".join(chars)

    if a.pick is None:
        svg, w, h = sheet(variants, css, f"{a.text} — {what} 견본 (마음에 드는 번호를 골라 주세요)")
        target = out / f"{stem}-{what}-견본.svg"
        target.write_text(svg, encoding="utf-8")
        print(f"견본 {len(variants)}종: {target}")
        png = target.with_suffix(".png")
        if to_png(svg, png, w, h, transparent=False):
            print(f"견본 그림: {png}")
        for i, (label, _) in enumerate(variants, 1):
            print(f"  {i}번 {label}")
        return
    if not 1 <= a.pick <= len(variants):
        sys.exit(f"견본 번호는 1부터 {len(variants)}까지입니다.")
    label, inner = variants[a.pick - 1]
    svg = svg_doc(inner, S, S, css)
    target = out / f"{stem}-{what}.svg"
    target.write_text(svg, encoding="utf-8")
    print(f"{a.pick}번 ({label}): {target}")
    png = target.with_suffix(".png")
    if to_png(svg, png, S, S, transparent=True):
        print(f"바탕이 투명한 그림: {png}")


if __name__ == "__main__":
    main()
