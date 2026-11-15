"""sheet.py — draw.py가 쓰는 A4 가로 도면(SVG) 조판.

왼쪽에 도면, 오른쪽에 표제·방위표·개요표·주기를 둔다. 길이는 종이 위 mm, 도면 좌표는 미터.
"""
import math

FONT = "'Apple SD Gothic Neo','Malgun Gothic','Noto Sans CJK KR','NanumGothic',sans-serif"
SCALES = (20, 30, 40, 50, 60, 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, 2500, 3000, 5000, 6000, 10000)
AREA = (14, 30, 180, 166)               # 도면 자리: x, y, 너비, 높이
CLIP = (10, 24, 186, 176)               # 도면과 바탕이 보이는 네모
AREA_GAP = 0.02                         # 대장 면적과 도면에서 잰 넓이가 이보다 더 다르면 알린다
PANEL_X, PANEL_R = 204, 285
FILL = {"기존": "#EDEDED", "신설": "#F3E7C2", "칸": "none"}
STROKE = {"기존": 0.35, "신설": 0.6, "칸": 0.2}
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
LETTERS = "가나다라마바사아자차카타파하"
DIM_SIDES = {"아래": (0, 1), "위": (3, 2), "왼쪽": (0, 3), "오른쪽": (1, 2)}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text_width(s, size):
    return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in str(s)) * size


def text(x, y, s, size=2.6, weight="normal", anchor="middle", fill="#111", rot=None):
    tr = f' transform="rotate({rot:.2f} {x:.2f} {y:.2f})"' if rot else ""
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill}"{tr}>{esc(s)}</text>')


def line(p, q, sw=0.2, dash=None, color="#222"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{p[0]:.2f}" y1="{p[1]:.2f}" x2="{q[0]:.2f}" y2="{q[1]:.2f}" stroke="{color}" stroke-width="{sw}"{d}/>'


def polygon(points, fill, sw=0.3, dash=None, color="#222", opacity=1):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return f'<polygon points="{pts}" fill="{fill}" fill-opacity="{opacity}" stroke="{color}" stroke-width="{sw}"{d}/>'


def wrap(s, width, size):
    """글을 너비(mm)에 맞춰 줄로 나눈다."""
    lines, cur = [], ""
    for ch in str(s):
        if cur and text_width(cur + ch, size) > width:
            lines, cur = lines + [cur], ch.lstrip()
        else:
            cur += ch
    return lines + ([cur] if cur else [])


def mm_label(meters):
    return f"{round(meters * 1000):,}"


def all_points(spec, corners):
    pts = [p for b in spec["건물"] for p in corners(b)]
    pts += [tuple(p) for p in spec.get("대지경계") or []]
    for m in spec.get("표시", []):
        if m["종류"] in ("도로", "구역"):
            pts += corners(m)
        elif m["종류"] == "글자":
            pts.append(tuple(m["위치"]))
        else:
            pts += [tuple(m["시작"]), tuple(m["끝"])]
    return pts + [tuple(d[k]) for d in spec.get("치수", []) for k in ("시작", "끝")]


def make_view(spec, corners):
    """도면 자리에 들어가는 가장 큰 표준 축척을 고르고 가운데에 놓는다."""
    crop = spec.get("범위")
    pts = [(crop[0], crop[1]), (crop[2], crop[3])] if crop else all_points(spec, corners)
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    ax, ay, aw, ah = AREA
    margin = 14                                    # 치수선과 글자 자리 (mm)
    wanted = spec.get("축척")
    fits = [n for n in SCALES if (maxx - minx) * 1000 / n <= aw - 2 * margin and (maxy - miny) * 1000 / n <= ah - 2 * margin]
    scale = wanted if wanted else (fits[0] if fits else SCALES[-1])
    s = 1000 / scale
    ox = ax + (aw - (maxx - minx) * s) / 2
    oy = ay + (ah - (maxy - miny) * s) / 2
    return {"scale": scale, "s": s, "ox": ox, "oy": oy, "minx": minx, "maxy": maxy}


def to_page(view, pt):
    return (view["ox"] + (pt[0] - view["minx"]) * view["s"], view["oy"] + (view["maxy"] - pt[1]) * view["s"])


def centroid(points):
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def dimension(view, p, q, offset=5, away_from=None):
    """두 점 사이 치수선. 글자는 실제 거리(mm). away_from(종이 좌표)이 있으면 그 반대쪽으로 띄운다."""
    a, b = to_page(view, p), to_page(view, q)
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length < 1e-6:
        return []
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    nx, ny = -uy, ux
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    if away_from and (mid[0] - away_from[0]) * nx + (mid[1] - away_from[1]) * ny < 0:
        nx, ny = -nx, -ny
    elif not away_from and (ny > 0 or (abs(ny) < 1e-9 and nx > 0)):
        nx, ny = -nx, -ny                          # 기본은 위쪽·왼쪽
    a2, b2 = (a[0] + nx * offset, a[1] + ny * offset), (b[0] + nx * offset, b[1] + ny * offset)
    out = [line(a, (a2[0] + nx, a2[1] + ny), 0.1, color="#555"), line(b, (b2[0] + nx, b2[1] + ny), 0.1, color="#555"),
           line(a2, b2, 0.15)]
    out += [f'<circle cx="{c[0]:.2f}" cy="{c[1]:.2f}" r="0.35" fill="#222"/>' for c in (a2, b2)]
    angle = math.degrees(math.atan2(uy, ux))
    if angle > 90 - 1e-6:                          # 세로 치수는 아래에서 위로 읽히게 돌린다
        angle -= 180
    elif angle < -90 - 1e-6:
        angle += 180
    up = -1 if (nx * math.sin(math.radians(angle)) - ny * math.cos(math.radians(angle))) > 0 else 1
    tx, ty = (a2[0] + b2[0]) / 2 + nx * 1.0, (a2[1] + b2[1]) / 2 + ny * 1.0
    if up > 0:                                     # 글자가 치수선 아래쪽에 놓일 때는 글자 높이만큼 더 띄운다
        tx, ty = tx + nx * 1.6, ty + ny * 1.6
    label = mm_label(math.hypot(q[0] - p[0], q[1] - p[1]))
    return out + [text(tx, ty, label, 2.1, rot=angle)]


def door_marks(view, building, pts):
    """벽에 낸 문·창: 흰 틈과 양끝 눈금, 이름."""
    edges = {"아래": (pts[0], pts[1]), "오른쪽": (pts[1], pts[2]), "위": (pts[3], pts[2]), "왼쪽": (pts[0], pts[3])}
    centre = to_page(view, centroid(pts))
    out = []
    for door in building.get("문", []):
        p, q = edges[door["벽"]]
        run = math.hypot(q[0] - p[0], q[1] - p[1])
        ux, uy = (q[0] - p[0]) / run, (q[1] - p[1]) / run
        a = to_page(view, (p[0] + ux * door["띄움"], p[1] + uy * door["띄움"]))
        b = to_page(view, (p[0] + ux * (door["띄움"] + door["폭"]), p[1] + uy * (door["띄움"] + door["폭"])))
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        dist = math.hypot(mid[0] - centre[0], mid[1] - centre[1]) or 1
        nx, ny = (mid[0] - centre[0]) / dist, (mid[1] - centre[1]) / dist
        px, py = (b[1] - a[1], a[0] - b[0])
        plen = math.hypot(px, py) or 1
        px, py = px / plen * 1.2, py / plen * 1.2
        out += [line(a, b, 1.1, color="#fff"), line((a[0] - px, a[1] - py), (a[0] + px, a[1] + py), 0.3),
                line((b[0] - px, b[1] - py), (b[0] + px, b[1] + py), 0.3)]
        label = f"{door.get('이름', '문')} {mm_label(door['폭'])}"
        anchor = "start" if nx > 0.5 else "end" if nx < -0.5 else "middle"
        out.append(text(mid[0] + nx * 3.2, mid[1] + ny * 3.2 + 0.8, label, 2.0, anchor=anchor))
    return out


def tag_buildings(spec):
    """신설은 ①②…, 기존은 가나다… 표를 붙인다. 칸은 표가 없다."""
    counts = {"신설": 0, "기존": 0}
    out = []
    for b in spec["건물"]:
        group = b["구분"]
        if group == "칸":
            out.append({**b, "표": ""})
            continue
        marks = CIRCLED if group == "신설" else LETTERS
        i = counts[group]
        out.append({**b, "표": marks[i] if i < len(marks) else str(i + 1)})
        counts = {**counts, group: i + 1}
    return out


def building_marks(view, b, corners, area, with_dims):
    pts = corners(b)
    page = [to_page(view, p) for p in pts]
    group = b["구분"]
    out = [polygon(page, FILL[group], STROKE[group], dash="1.2 0.8" if group == "칸" else None)]
    xs, ys = [p[0] for p in page], [p[1] for p in page]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    name = f"{b['표']} {b['이름']}".strip()
    size = 3.0 if group == "신설" else 2.6
    weight = "normal" if group == "칸" else "bold"
    if text_width(name, size) <= width - 2 and height >= size * 1.5:
        sub = f"{area(pts):,.2f}㎡"
        roomy = height >= size * 3.2 and text_width(sub, 2.1) <= width - 2
        out.append(text(cx, cy + (0 if roomy else size * 0.35), name, size, weight))
        out += [text(cx, cy + size * 1.25, sub, 2.1, fill="#444")] if roomy else []
    elif b["표"]:
        out.append(text(cx, cy + 1.0, b["표"], min(size, max(height * 0.8, 1.8)), "bold"))
    if with_dims and "꼭짓점" not in b:
        offset = 9 if b.get("문") else 4            # 문 이름이 놓일 자리를 비운다
        for key, default in (("가로치수", "아래"), ("세로치수", "왼쪽")):
            side = b.get(key, default)
            if side in DIM_SIDES:
                i, j = DIM_SIDES[side]
                out += dimension(view, pts[i], pts[j], offset, (cx, cy))
    return out + door_marks(view, b, pts)


def extra_marks(view, spec, corners):
    out = []
    for m in spec.get("표시", []):
        kind = m["종류"]
        if kind in ("도로", "구역"):
            page = [to_page(view, p) for p in corners(m)]
            fill, dash = ("#DADADA", None) if kind == "도로" else ("#CFE6F7", "1.5 1")
            out.append(polygon(page, fill, 0.2, dash, "#666", 0.6))
            cx, cy = centroid(page)
            out += [text(cx, cy + 0.9, m["이름"], 2.3, fill="#333")] if m.get("이름") else []
        elif kind == "글자":
            x, y = to_page(view, m["위치"])
            out.append(text(x, y, m["글"], m.get("크기", 2.4), fill="#333"))
        else:
            a, b = to_page(view, m["시작"]), to_page(view, m["끝"])
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            wing = [(b[0] - 2.6 * math.cos(ang + s), b[1] - 2.6 * math.sin(ang + s)) for s in (0.45, -0.45)]
            out += [line(a, b, 0.4, color="#2F5F8A"), polygon([b] + wing, "#2F5F8A", 0, color="#2F5F8A")]
            out += [text(a[0], a[1] + (3.6 if b[1] < a[1] else -1.6), m["글"], 2.3, "bold", fill="#2F5F8A")] if m.get("글") else []
    return out


def compass(cx, cy, north_deg, r=8):
    """방위표. north_deg는 종이 위쪽에서 시계 방향으로 잰 북쪽의 각도."""
    a = math.radians(north_deg)
    tip = (cx + r * math.sin(a), cy - r * math.cos(a))
    tail = (cx - r * math.sin(a), cy + r * math.cos(a))
    side = [(cx + 2 * math.cos(a), cy + 2 * math.sin(a)), (cx - 2 * math.cos(a), cy - 2 * math.sin(a))]
    label = (cx + (r + 3.2) * math.sin(a), cy - (r + 3.2) * math.cos(a) + 1.4)
    return [f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#222" stroke-width="0.3"/>',
            polygon([tip] + side, "#222", 0.2), polygon([tail] + side, "#fff", 0.2),
            text(label[0], label[1], "N", 4.0, "bold")]


def summary_rows(y, buildings, corners, area):
    """개요표: 신설 건물은 용도·구조·크기까지, 기존 건물은 이름과 면적."""
    out = []
    new = [b for b in buildings if b["구분"] == "신설"]
    old = [b for b in buildings if b["구분"] == "기존"]
    for title, group in (("신청 건축물", new), ("기존 건축물", old)):
        if not group:
            continue
        out.append(text(PANEL_X, y, title, 2.9, "bold", "start"))
        y += 5
        for b in group:
            head = f"{b['표']} {b['이름']}" + (f" · {b['용도']}" if b.get("용도") else "")
            drawn = area(corners(b))
            shown = b.get("대장면적") or drawn
            out += [text(PANEL_X, y, head, 2.5, "bold" if b["구분"] == "신설" else "normal", "start"),
                    text(PANEL_R, y, f"{shown:,.2f}㎡", 2.5, anchor="end")]
            size = f"{b['가로']:g} × {b['세로']:g}m" if "가로" in b else ""
            ledger = f"대장 면적 (도면 {drawn:,.1f}㎡)" if b.get("대장면적") else ""
            detail = " · ".join(v for v in (b.get("구조", ""), size, b.get("설명", ""), ledger) if v)
            if detail:
                y += 3.6
                out.append(text(PANEL_X + 3.5, y, detail, 2.1, anchor="start", fill="#444"))
            y += 4.8
        total = sum(b.get("대장면적") or area(corners(b)) for b in group)
        out += [line((PANEL_X, y - 2.6), (PANEL_R, y - 2.6), 0.2),
                text(PANEL_X, y + 1.2, "바닥면적 합계", 2.5, "bold", "start"),
                text(PANEL_R, y + 1.2, f"{total:,.2f}㎡", 2.5, "bold", "end")]
        y += 8
    return out, y


def panel(spec, buildings, scale, corners, area, extra_notes=()):
    out = [text(PANEL_X, 20, spec["제목"], 4.4, "bold", "start")]
    y = 26
    head = [spec["주소"], spec.get("용도", ""), f"축척 1/{scale} (A4) · 치수 mm"]
    for s in (h for h in head if h):
        for ln in wrap(s, PANEL_R - PANEL_X, 2.5):
            out.append(text(PANEL_X, y, ln, 2.5, anchor="start"))
            y += 4
    out += compass((PANEL_X + PANEL_R) / 2, y + 13, spec["방위각"]) + [line((PANEL_X, y + 27), (PANEL_R, y + 27), 0.3)]
    rows, y = summary_rows(y + 33, buildings, corners, area)
    out += rows
    if spec.get("대지면적"):
        source = f" ({spec['대지면적출처']})" if spec.get("대지면적출처") else ""
        out.append(text(PANEL_X, y, f"대지면적 {spec['대지면적']:,g}㎡{source}", 2.5, anchor="start"))
        y += 4
        if spec.get("대지경계"):
            measured = area([tuple(p) for p in spec["대지경계"]])
            out.append(text(PANEL_X, y, f"경계선으로 잰 넓이 {measured:,.1f}㎡", 2.2, anchor="start", fill="#444"))
            y += 4
        y += 2
    notes = list(spec.get("주기", [])) + list(extra_notes)
    notes += [f"위치 근거: {spec['위치근거']}"] if spec.get("위치근거") else []
    notes += ["신청인이 직접 그린 도면이며 측량 성과가 아님"]
    for note in notes:
        for i, ln in enumerate(wrap(note, PANEL_R - PANEL_X - 3, 2.2)):
            if y > 190:
                break
            out.append(text(PANEL_X + (0 if i == 0 else 3), y, ("· " if i == 0 else "") + ln, 2.2, anchor="start", fill="#333"))
            y += 3.8
    foot = " · ".join(v for v in (f"작성일 {spec['작성일']}" if spec.get("작성일") else "",
                                 f"작성자 {spec['작성자']}" if spec.get("작성자") else "") if v)
    return out + ([text(PANEL_R, 199, foot, 2.3, anchor="end")] if foot else [])


def render(spec, corners, area, background=None):
    """도면 한 장의 SVG 글과 고른 축척을 돌려준다. background는 바탕 지도를 만드는 함수(없어도 된다)."""
    view = make_view(spec, corners)
    under, extra_notes, halo = background(spec, view, CLIP, lambda pt: to_page(view, pt)) if background else ([], [], False)
    buildings = tag_buildings(spec)
    floor_plan = spec["종류"] == "평면도"
    body = extra_marks(view, spec, corners)
    border = spec.get("대지경계")
    if border:
        page = [to_page(view, p) for p in border]
        body.append(polygon(page, "none", 0.45, "6 1.5 1 1.5", "#B03030"))
        top = min(page, key=lambda p: p[1])
        body.append(text(top[0] + 2, top[1] - 1.5, "대지경계선", 2.2, anchor="start", fill="#B03030"))
    for b in buildings:
        body += building_marks(view, b, corners, area, b["구분"] != "칸" or floor_plan)
    for d in spec.get("치수", []):
        body += dimension(view, d["시작"], d["끝"], d.get("띄움", 0))
    frame = ('<rect width="297" height="210" fill="#fff"/>'
             '<rect x="8" y="8" width="281" height="194" fill="none" stroke="#222" stroke-width="0.5"/>'
             + line((198, 8), (198, 202), 0.3))
    cx, cy, cw, ch = CLIP
    style = "<style>.halo text{paint-order:stroke;stroke:#fff;stroke-width:0.9px;stroke-linejoin:round}</style>"
    clip = (f'{style}<defs><clipPath id="drawing"><rect x="{cx}" y="{cy}" width="{cw}" height="{ch}"/></clipPath></defs>'
            '<g clip-path="url(#drawing)">' + "".join(under)
            + f'<g class="{"halo" if halo else ""}">' + "".join(body) + "</g></g>")
    cropped = [text(AREA[0], 20, "대지의 일부만 그린 도면 (범위 밖은 생략)", 2.4, anchor="start", fill="#444")] if spec.get("범위") else []
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">'
           + frame + clip + "".join(cropped)
           + "".join(panel(spec, buildings, view["scale"], corners, area, extra_notes)) + "</svg>")
    return svg, view["scale"]
