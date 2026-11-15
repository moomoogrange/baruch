#!/usr/bin/env python3
"""draw.py — 신청 서류에 붙이는 배치도·평면도·현황도 그리기 (바룩 site-drawing 스킬)

치수를 적은 JSON 파일 하나를 받아 A4 가로 도면(SVG, PDF, PNG)을 만든다.
파이썬 3만 있으면 SVG가 나온다. PDF와 PNG는 크롬이나 엣지가 있어야 한다.

  draw.py example 배치도 > 배치도.json     보기 파일 만들기 (배치도 · 평면도)
  draw.py check 배치도.json                적힌 값만 점검
  draw.py make 배치도.json                 도면 만들기 (같은 폴더에 .svg .pdf .png)
  draw.py make 배치도.json --out 첨부       다른 폴더에 만들기

좌표와 길이는 모두 미터다. x는 도면의 오른쪽, y는 도면의 위쪽으로 커진다.
적는 칸은 example 로 나오는 보기 파일과 스킬 문서(SKILL.md)에 있다.
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sheet import render  # noqa: E402

KINDS = ("배치도", "평면도", "현황도")
GROUPS = ("기존", "신설", "칸")
WALLS = ("아래", "오른쪽", "위", "왼쪽")
NORTH = {"위": 0, "오른쪽": 90, "아래": 180, "왼쪽": 270}

EXAMPLES = {
    "배치도": {
        "종류": "배치도", "제목": "가설건축물 배치도", "용도": "가설건축물 축조신고용",
        "주소": "○○시 ○○동 000-0", "작성일": "2026-01-01", "작성자": "",
        "방위": "위", "대지면적": 1200,
        "위치근거": "신청인이 현장에서 줄자로 잰 치수 (2026-01-01)",
        "대지경계": [[0, 0], [40, 0], [40, 30], [0, 30]],
        "건물": [
            {"이름": "기존 창고", "구분": "기존", "위치": [4, 12], "가로": 15, "세로": 10},
            {"이름": "가설1동", "구분": "신설", "용도": "임시창고", "구조": "컨테이너",
             "위치": [24, 14], "가로": 6, "세로": 3, "세로치수": "오른쪽"},
        ],
        "표시": [
            {"종류": "도로", "이름": "도로 (너비 6m)", "위치": [0, -6], "가로": 40, "세로": 6},
            {"종류": "화살표", "시작": [30, -3], "끝": [30, 6], "글": "출입"},
        ],
        "치수": [
            {"시작": [19, 17], "끝": [24, 17]},
            {"시작": [26, 0], "끝": [26, 14]},
            {"시작": [30, 14], "끝": [40, 14]},
        ],
        "주기": ["기초 없이 받침 위에 올려놓음"],
    },
    "평면도": {
        "종류": "평면도", "제목": "가설건축물 평면도", "용도": "가설건축물 축조신고용",
        "주소": "○○시 ○○동 000-0", "작성일": "2026-01-01", "작성자": "", "방위": "위",
        "건물": [
            {"이름": "가설1동", "구분": "신설", "용도": "임시창고", "구조": "컨테이너",
             "위치": [0, 0], "가로": 6, "세로": 3,
             "문": [{"벽": "아래", "띄움": 2.5, "폭": 0.9, "이름": "출입문"},
                   {"벽": "위", "띄움": 1.0, "폭": 1.2, "이름": "창"}]},
        ],
        "주기": ["지상 1층, 내부 칸막이 없음"],
    },
}


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def is_point(v):
    return isinstance(v, list) and len(v) == 2 and all(is_num(c) for c in v)


def corners(shape):
    """꼭짓점 목록. 사각형은 위치(왼쪽 아래 모서리)·가로·세로·회전(시계 반대 방향, 도)으로 만든다."""
    if "꼭짓점" in shape:
        return [tuple(p) for p in shape["꼭짓점"]]
    x, y = shape["위치"]
    w, h = shape["가로"], shape["세로"]
    a = math.radians(shape.get("회전", 0))
    cos, sin = math.cos(a), math.sin(a)
    return [(x + dx * cos - dy * sin, y + dx * sin + dy * cos) for dx, dy in ((0, 0), (w, 0), (w, h), (0, h))]


def area(points):
    total = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))
    return abs(total) / 2


def inside(pt, polygon):
    x, y = pt
    hit = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            hit = not hit
    return hit


def crosses(p, q, r, s):
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    eps = 1e-9
    return side(p, q, r) * side(p, q, s) < -eps and side(r, s, p) * side(r, s, q) < -eps


def overlaps(a, b):
    edges_a = list(zip(a, a[1:] + a[:1]))
    edges_b = list(zip(b, b[1:] + b[:1]))
    if any(crosses(p, q, r, s) for p, q in edges_a for r, s in edges_b):
        return True
    centre = lambda pts: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return inside(centre(a), b) or inside(centre(b), a)


def shape_errors(shape, label):
    if "꼭짓점" in shape:
        pts = shape["꼭짓점"]
        ok = isinstance(pts, list) and len(pts) >= 3 and all(is_point(p) for p in pts)
        return [] if ok else [f"{label}: 꼭짓점은 [x, y] 셋 이상이어야 합니다."]
    out = []
    if not is_point(shape.get("위치")):
        out.append(f"{label}: 위치 [x, y]가 없습니다.")
    for key in ("가로", "세로"):
        if not is_num(shape.get(key)) or shape.get(key, 0) <= 0:
            out.append(f"{label}: {key}는 0보다 큰 숫자(미터)여야 합니다.")
    if "회전" in shape and not is_num(shape["회전"]):
        out.append(f"{label}: 회전은 숫자(도)여야 합니다.")
    return out


def door_errors(building, label):
    out = []
    for door in building.get("문", []):
        if "꼭짓점" in building:
            return [f"{label}: 문은 가로·세로로 적은 사각형 건물에만 그립니다."]
        if door.get("벽") not in WALLS:
            out.append(f"{label}: 문의 벽은 {' · '.join(WALLS)} 가운데 하나입니다.")
            continue
        run = building["가로"] if door["벽"] in ("아래", "위") else building["세로"]
        if not is_num(door.get("띄움")) or not is_num(door.get("폭")) or door.get("폭", 0) <= 0:
            out.append(f"{label}: 문의 띄움과 폭을 숫자(미터)로 적습니다.")
        elif door["띄움"] < 0 or door["띄움"] + door["폭"] > run + 1e-9:
            out.append(f"{label}: 문이 벽 길이({run:g}m)를 벗어납니다.")
    return out


def building_errors(spec):
    buildings = spec.get("건물")
    if not isinstance(buildings, list) or not buildings:
        return ["건물이 하나도 없습니다."]
    out = []
    for i, b in enumerate(buildings, 1):
        label = f"건물 {i}({b.get('이름', '이름 없음')})"
        if not b.get("이름"):
            out.append(f"{label}: 이름이 없습니다.")
        if b.get("구분") not in GROUPS:
            out.append(f"{label}: 구분은 {' · '.join(GROUPS)} 가운데 하나입니다.")
        for key, sides in (("가로치수", ("아래", "위", "없음")), ("세로치수", ("왼쪽", "오른쪽", "없음"))):
            if key in b and b[key] not in sides:
                out.append(f"{label}: {key}는 {' · '.join(sides)} 가운데 하나입니다.")
        errs = shape_errors(b, label)
        out += errs + ([] if errs else door_errors(b, label))
    return out


def extra_errors(spec):
    out = []
    for i, m in enumerate(spec.get("표시", []), 1):
        kind = m.get("종류")
        if kind in ("도로", "구역"):
            out += shape_errors(m, f"표시 {i}({kind})")
        elif kind == "글자":
            out += [] if is_point(m.get("위치")) and m.get("글") else [f"표시 {i}(글자): 위치와 글이 필요합니다."]
        elif kind == "화살표":
            out += [] if is_point(m.get("시작")) and is_point(m.get("끝")) else [f"표시 {i}(화살표): 시작과 끝이 필요합니다."]
        else:
            out.append(f"표시 {i}: 종류는 도로 · 구역 · 글자 · 화살표 가운데 하나입니다.")
    for i, d in enumerate(spec.get("치수", []), 1):
        if not (is_point(d.get("시작")) and is_point(d.get("끝"))) or d.get("시작") == d.get("끝"):
            out.append(f"치수 {i}: 서로 다른 시작과 끝 [x, y]가 필요합니다.")
    border = spec.get("대지경계")
    if border is not None and not (isinstance(border, list) and len(border) >= 3 and all(is_point(p) for p in border)):
        out.append("대지경계는 [x, y] 셋 이상이어야 합니다.")
    return out


def errors(spec):
    out = []
    if spec.get("종류") not in KINDS:
        out.append(f"종류는 {' · '.join(KINDS)} 가운데 하나입니다.")
    for key in ("제목", "주소"):
        if not str(spec.get(key, "")).strip():
            out.append(f"{key}이(가) 비어 있습니다.")
    north = spec.get("방위")
    if north not in NORTH and not is_num(north):
        out.append("방위가 없습니다. 도면에서 북쪽이 어느 쪽인지(위 · 오른쪽 · 아래 · 왼쪽) 또는 "
                   "위에서 시계 방향으로 몇 도인지 적습니다. 모르면 그리지 말고 신청인에게 묻습니다.")
    if spec.get("종류") in ("배치도", "현황도") and not str(spec.get("위치근거", "")).strip():
        out.append("위치근거가 비어 있습니다. 건물 자리와 거리를 어디서 얻었는지 적습니다 "
                   "(현장에서 잰 치수, 지적도, 측량 성과도 등). 근거 없이 자리를 짐작해 그리지 않습니다.")
    return out + building_errors(spec) + extra_errors(spec)


def warnings(spec):
    out = []
    buildings = [(b, corners(b)) for b in spec["건물"] if b["구분"] != "칸"]
    for i, (b, pts) in enumerate(buildings):
        for other, other_pts in buildings[i + 1:]:
            if "신설" in (b["구분"], other["구분"]) and overlaps(pts, other_pts):
                out.append(f"'{b['이름']}'과 '{other['이름']}'이 겹칩니다.")
    border = spec.get("대지경계")
    if border:
        polygon = [tuple(p) for p in border]
        out += [f"'{b['이름']}'이 대지경계 밖으로 나갑니다." for b, pts in buildings
                if not all(inside(p, polygon) for p in pts)]
    elif spec["종류"] == "배치도":
        out.append("대지경계를 그리지 않았습니다. 경계선에서 건물까지의 거리를 보려는 관청이 많습니다.")
    if spec["종류"] == "배치도" and not any(m.get("종류") == "도로" for m in spec.get("표시", [])):
        out.append("도로 표시가 없습니다. 대지에 닿은 도로나 진입로가 있으면 너비와 함께 그립니다.")
    if spec["종류"] == "배치도" and not spec.get("치수"):
        out.append("거리 치수가 없습니다. 기존 건물이나 경계선에서 새 건물까지의 거리를 적습니다.")
    return out


def load(path):
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        die(f"파일을 읽지 못했습니다: {path} ({e})")
    if not isinstance(spec, dict):
        die("파일 내용이 { } 로 시작하는 JSON이어야 합니다.")
    found = errors(spec)
    if found:
        die("고쳐야 그릴 수 있습니다.\n" + "\n".join(f"  - {e}" for e in found))
    return {**spec, "방위각": NORTH.get(spec["방위"], spec["방위"])}


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


def export(svg, pdf, png, browser):
    """SVG 글을 크롬으로 A4 가로 PDF와 미리보기 PNG로 바꾼다."""
    style = "@page{size:297mm 210mm;margin:0}html,body{margin:0;background:#fff}svg{display:block;width:297mm;height:210mm}"
    with tempfile.TemporaryDirectory() as td:
        html = Path(td) / "sheet.html"
        html.write_text(f'<!doctype html><meta charset="utf-8"><style>{style}</style>{svg}', encoding="utf-8")
        base = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={td}/profile"]
        jobs = ((pdf, ["--no-pdf-header-footer", f"--print-to-pdf={pdf.resolve()}"]),
                (png, ["--hide-scrollbars", "--window-size=1123,794", "--force-device-scale-factor=2",
                       f"--screenshot={png.resolve()}"]))
        for target, flags in jobs:
            try:
                subprocess.run(base + flags + [html.as_uri()], capture_output=True, timeout=90, check=False)
            except (OSError, subprocess.TimeoutExpired) as e:
                print(f"  {target.name}을 만들지 못했습니다 ({e}).", file=sys.stderr)
    return [t for t in (pdf, png) if t.exists() and t.stat().st_size > 0]


def make(path, outdir):
    spec = load(path)
    notes = warnings(spec)
    svg, scale = render(spec, corners, area)
    out = Path(outdir) if outdir else Path(path).resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(path).stem
    target = out / f"{stem}.svg"
    target.write_text(svg, encoding="utf-8")
    made = [target]
    browser = find_browser()
    if browser:
        made += export(svg, out / f"{stem}.pdf", out / f"{stem}.png", browser)
    print(f"{spec['종류']} · 축척 1/{scale} · A4 가로")
    for f in made:
        print(f"  {f}")
    if not browser:
        print("  크롬이나 엣지를 찾지 못해 PDF를 만들지 못했습니다. SVG를 브라우저로 열어 A4 가로, 여백 없음으로 인쇄하면 됩니다.")
    for n in notes:
        print(f"  [살필 것] {n}")
    print("  PNG를 열어 건물 자리, 방위, 치수 글자가 겹치지 않는지 눈으로 확인하십시오.")


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
    elif a[0] == "example" and len(a) == 2 and a[1] in EXAMPLES:
        print(json.dumps(EXAMPLES[a[1]], ensure_ascii=False, indent=2))
    elif a[0] == "check" and len(a) == 2:
        spec = load(a[1])
        notes = warnings(spec)
        print("그릴 수 있습니다." + ("" if notes else " 살필 것이 없습니다."))
        for n in notes:
            print(f"  [살필 것] {n}")
    elif a[0] == "make" and len(a) in (2, 4) and (len(a) == 2 or a[2] == "--out"):
        make(a[1], a[3] if len(a) == 4 else None)
    else:
        die(__doc__)


if __name__ == "__main__":
    main()
