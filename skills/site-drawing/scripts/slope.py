#!/usr/bin/env python3
"""slope.py — 경사 참고도 그리기 (바룩 site-drawing 스킬)

위도와 경도를 받아 그 둘레 땅의 경사와 등고선을 A4 가로 한 장(SVG, PDF, PNG)으로 만든다.
인증키가 필요 없는 공개 표고 자료(AWS Terrain Tiles, 격자 약 30m)를 쓴다. 인터넷이 필요하다.

  slope.py make 37.6586 126.9779                         가운데 좌표(위도 경도), 한 변 300m
  slope.py make 37.6586 126.9779 --size 500              한 변 500m (200 ~ 3000)
  slope.py make 37.6586 126.9779 --address "○○시 ○○동 000" --out 첨부

참고용이다. 격자가 성겨 건물 한 채 크기의 경사는 알 수 없고,
산지전용 등에 내는 평균경사도 조사서를 대신하지 못한다.
"""
import math
import struct
import sys
import urllib.error
import urllib.request
import zlib
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from draw import die, export, find_browser  # noqa: E402
from sheet import compass, line, text, wrap  # noqa: E402

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 13                                      # 화소 약 15m — 원자료(약 30m)보다 촘촘하게 읽어 보간한다
CELLS = 48                                     # 한 변을 나누는 칸 수
BASE = 30.0                                    # 경사를 재는 거리 (m) — 원자료 격자 크기
CLASSES = ((5, "#F7F4D5"), (10, "#EFE29A"), (15, "#EBC464"), (20, "#E39A45"), (25, "#D4622F"), (91, "#A82A22"))
MAP_X, MAP_Y, MAP_SIDE = 26, 34, 152           # 지도 자리 (mm)
PANEL_X, PANEL_R = 204, 285
LIMIT_DEG = 25                                 # 산지전용허가기준의 평균경사도 (산지관리법 시행령 별표 4)


def unfilter(kind, cur, prev, bpp):
    """PNG 한 줄의 필터를 푼다."""
    out = bytearray(cur)
    for i in range(len(out)):
        a = out[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        if kind == 1:
            add = a
        elif kind == 2:
            add = b
        elif kind == 3:
            add = (a + b) // 2
        elif kind == 4:
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            add = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
        else:
            add = 0
        out[i] = (out[i] + add) & 255
    return out


def decode_png(data):
    """8비트 RGB·RGBA PNG를 (너비, 높이, 화소당 바이트, 줄 목록)으로 푼다."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG가 아닙니다")
    pos, idat, head = 8, [], None
    while pos < len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + size]
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        pos += 12 + size
    width, height, depth, color = head[0], head[1], head[2], head[3]
    if depth != 8 or color not in (2, 6):
        raise ValueError(f"읽을 수 없는 PNG 형식입니다 (depth {depth}, color {color})")
    bpp = 3 if color == 2 else 4
    raw = zlib.decompress(b"".join(idat))
    stride = width * bpp
    rows, prev = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        prev = unfilter(raw[start], raw[start + 1:start + 1 + stride], prev, bpp)
        rows.append(prev)
    return width, height, bpp, rows


def fetch_tile(x, y):
    url = TILE_URL.format(z=ZOOM, x=x, y=y)
    req = urllib.request.Request(url, headers={"User-Agent": "baruch-slope/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return decode_png(r.read())


def global_pixel(lat, lon):
    n = 256 * 2 ** ZOOM
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def make_sampler():
    """위도·경도의 표고(m)를 돌려주는 함수. 타일은 한 번만 받는다."""
    tiles = {}

    def pixel(px, py):
        key = (px // 256, py // 256)
        if key not in tiles:
            tiles[key] = fetch_tile(*key)
        _, _, bpp, rows = tiles[key]
        row, i = rows[py % 256], (px % 256) * bpp
        return row[i] * 256 + row[i + 1] + row[i + 2] / 256 - 32768

    def elevation(lat, lon):
        x, y = global_pixel(lat, lon)
        x0, y0 = math.floor(x - 0.5), math.floor(y - 0.5)
        fx, fy = x - 0.5 - x0, y - 0.5 - y0
        top = pixel(x0, y0) * (1 - fx) + pixel(x0 + 1, y0) * fx
        bottom = pixel(x0, y0 + 1) * (1 - fx) + pixel(x0 + 1, y0 + 1) * fx
        return top * (1 - fy) + bottom * fy

    return elevation


def survey(lat, lon, size):
    """가운데 좌표 둘레 size×size 미터의 표고 격자와 칸마다의 경사(도).

    grid[j][i]와 slopes[j][i]에서 j는 북→남, i는 서→동. 경사는 칸 가운데에서 동서·남북으로
    BASE 미터씩 떨어진 표고의 차이로 잰다. 원자료 격자보다 좁게 재면 잡음만 커진다.
    """
    elevation = make_sampler()
    step = size / CELLS
    per_lat = 111320.0
    per_lon = 111320.0 * math.cos(math.radians(lat))

    def at(east, north):
        return elevation(lat + north / per_lat, lon + east / per_lon)

    grid = [[at(-size / 2 + i * step, size / 2 - j * step) for i in range(CELLS + 1)] for j in range(CELLS + 1)]
    slopes = []
    for j in range(CELLS):
        north = size / 2 - (j + 0.5) * step
        row = []
        for i in range(CELLS):
            east = -size / 2 + (i + 0.5) * step
            dx = (at(east + BASE, north) - at(east - BASE, north)) / (2 * BASE)
            dy = (at(east, north + BASE) - at(east, north - BASE)) / (2 * BASE)
            row.append(math.degrees(math.atan(math.hypot(dx, dy))))
        slopes.append(row)
    return grid, slopes


def summarize(grid, slopes):
    flat = [s for row in slopes for s in row]
    heights = [h for row in grid for h in row]
    shares, low = [], 0
    for top, _ in CLASSES:
        shares.append(sum(1 for s in flat if low <= s < top) / len(flat) * 100)
        low = top
    mean = sum(flat) / len(flat)
    return {"평균": mean, "평균퍼센트": math.tan(math.radians(mean)) * 100, "최대": max(flat),
            "최저표고": min(heights), "최고표고": max(heights), "비율": shares,
            "기준이상": sum(1 for s in flat if s >= LIMIT_DEG) / len(flat) * 100}


def contour_interval(span):
    for step in (1, 2, 5, 10, 20, 50, 100):
        if span / step <= 25:
            return step
    return 200


def contour_segments(grid, level):
    """등고선 한 줄(level)의 선분들. 칸 좌표(0~CELLS)로 돌려준다."""
    def cross(a, b, pa, pb):
        t = (level - a) / (b - a)
        return (pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t)

    out = []
    for j in range(CELLS):
        for i in range(CELLS):
            corners = (((i, j), grid[j][i]), ((i + 1, j), grid[j][i + 1]),
                       ((i + 1, j + 1), grid[j + 1][i + 1]), ((i, j + 1), grid[j + 1][i]))
            hits = []
            for (pa, a), (pb, b) in zip(corners, corners[1:] + corners[:1]):
                if (a < level) != (b < level):
                    hits.append(cross(a, b, pa, pb))
            out += [(hits[k], hits[k + 1]) for k in range(0, len(hits) - 1, 2)]
    return out


def color_of(slope):
    return next(color for top, color in CLASSES if slope < top)


def map_marks(grid, slopes, side):
    """경사 칸, 등고선, 가운데 표시."""
    cell = side / CELLS
    out = ['<g shape-rendering="crispEdges">']
    for j, row in enumerate(slopes):
        for i, s in enumerate(row):
            out.append(f'<rect x="{MAP_X + i * cell:.2f}" y="{MAP_Y + j * cell:.2f}" width="{cell + 0.05:.2f}" '
                       f'height="{cell + 0.05:.2f}" fill="{color_of(s)}"/>')
    out.append("</g>")
    heights = [h for r in grid for h in r]
    step = contour_interval(max(heights) - min(heights))
    level = math.ceil(min(heights) / step) * step
    while level < max(heights):
        bold = round(level / step) % 5 == 0
        for p, q in contour_segments(grid, level):
            out.append(line((MAP_X + p[0] * cell, MAP_Y + p[1] * cell), (MAP_X + q[0] * cell, MAP_Y + q[1] * cell),
                            0.3 if bold else 0.12, color="#5A4632"))
        level += step
    cx, cy = MAP_X + side / 2, MAP_Y + side / 2
    out += [f'<rect x="{MAP_X}" y="{MAP_Y}" width="{side:.2f}" height="{side:.2f}" fill="none" stroke="#222" stroke-width="0.4"/>',
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="2.2" fill="none" stroke="#111" stroke-width="0.5"/>',
            line((cx - 4, cy), (cx + 4, cy), 0.4, color="#111"), line((cx, cy - 4), (cx, cy + 4), 0.4, color="#111"),
            text(cx + 5, cy - 3, "대상 위치", 2.6, "bold", "start")]
    return out, step


def scale_bar(size, side):
    length = next(v for v in (500, 200, 100, 50, 20, 10) if v <= size / 3)
    width = length / size * side
    x, y = MAP_X, MAP_Y + side + 6
    return [line((x, y), (x + width, y), 0.5), line((x, y - 1.2), (x, y + 1.2), 0.4),
            line((x + width, y - 1.2), (x + width, y + 1.2), 0.4), text(x + width + 2, y + 0.9, f"{length}m", 2.4, anchor="start")]


def panel(opts, stats, scale, step):
    lat, lon, size = opts["lat"], opts["lon"], opts["size"]
    out = [text(PANEL_X, 20, "경사 참고도", 4.4, "bold", "start")]
    head = [opts["address"], f"가운데 북위 {lat:.5f} · 동경 {lon:.5f}", f"범위 {size:g} × {size:g}m · 축척 약 1/{scale:,} (A4)"]
    y = 26
    for s in (h for h in head if h):
        out.append(text(PANEL_X, y, s, 2.5, anchor="start"))
        y += 4
    out += compass((PANEL_X + PANEL_R) / 2, y + 13, 0) + [line((PANEL_X, y + 27), (PANEL_R, y + 27), 0.3)]
    y += 33
    out.append(text(PANEL_X, y, "경사 구간 (면적 비율)", 2.9, "bold", "start"))
    y, low = y + 5, 0
    for (top, color), share in zip(CLASSES, stats["비율"]):
        label = f"{low}° 이상 {top}° 미만" if top < 90 else f"{low}° 이상"
        out += [f'<rect x="{PANEL_X}" y="{y - 2.8:.2f}" width="5" height="3.6" fill="{color}" stroke="#222" stroke-width="0.15"/>',
                text(PANEL_X + 7, y, label, 2.4, anchor="start"), text(PANEL_R, y, f"{share:.1f}%", 2.4, anchor="end")]
        y, low = y + 4.6, top
    rows = (("평균 경사", f"{stats['평균']:.1f}° ({stats['평균퍼센트']:.0f}%)"), ("가장 급한 칸", f"{stats['최대']:.1f}°"),
            (f"{LIMIT_DEG}° 이상 면적", f"{stats['기준이상']:.1f}%"),
            ("표고", f"{stats['최저표고']:.0f} ~ {stats['최고표고']:.0f}m"), ("등고선 간격", f"{step}m (굵은 선 {step * 5}m)"))
    out.append(line((PANEL_X, y), (PANEL_R, y), 0.2))
    y += 5
    for name, value in rows:
        out += [text(PANEL_X, y, name, 2.5, "bold", "start"), text(PANEL_R, y, value, 2.5, anchor="end")]
        y += 4.6
    notes = ["참고용 도면임. 측량 성과나 평균경사도 조사서가 아님",
             "표고 자료의 격자가 약 30m라 건물 한 채 크기의 경사는 나타나지 않음",
             "표고에 나무와 건물의 높이가 섞여 있어 숲과 시가지는 실제보다 급하게 나올 수 있음",
             "자료: Mapzen Terrain Tiles (AWS Open Data), 원자료 SRTM 등"]
    y += 3
    for note in notes:
        for i, ln in enumerate(wrap(note, PANEL_R - PANEL_X - 3, 2.2)):
            out.append(text(PANEL_X + (0 if i == 0 else 3), y, ("· " if i == 0 else "") + ln, 2.2, anchor="start", fill="#333"))
            y += 3.8
    return out + [text(PANEL_R, 199, f"작성일 {date.today().isoformat()}", 2.3, anchor="end")]


def render(opts, grid, slopes, stats):
    size = opts["size"]
    side = MAP_SIDE
    scale = round(size * 1000 / side / 10) * 10
    marks, step = map_marks(grid, slopes, side)
    frame = ('<rect width="297" height="210" fill="#fff"/>'
             '<rect x="8" y="8" width="281" height="194" fill="none" stroke="#222" stroke-width="0.5"/>'
             + line((198, 8), (198, 202), 0.3))
    title = [text(MAP_X, 20, opts["address"] or "경사 참고도", 3.4, "bold", "start"),
             text(MAP_X, 26, "칸 색은 경사 구간, 선은 등고선 · 위쪽이 북", 2.4, anchor="start", fill="#444")]
    body = title + marks + scale_bar(size, side) + panel(opts, stats, scale, step)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">'
           + frame + "".join(body) + "</svg>")
    return svg, scale


def parse(args):
    opts = {"size": 300.0, "address": "", "out": "."}
    try:
        opts = {**opts, "lat": float(args[0]), "lon": float(args[1])}
        rest = args[2:]
        for key, value in zip(rest[::2], rest[1::2]):
            name = key.lstrip("-")
            if name not in ("size", "address", "out"):
                die(__doc__)
            opts = {**opts, name: float(value) if name == "size" else value}
        if len(rest) % 2:
            die(__doc__)
    except (IndexError, ValueError):
        die(__doc__)
    if not (33 <= opts["lat"] <= 39.5 and 124 <= opts["lon"] <= 132):
        die("위도와 경도가 우리나라 범위 밖입니다. 위도(33~39.5)를 먼저, 경도(124~132)를 다음에 적습니다.")
    if not 200 <= opts["size"] <= 3000:
        die("범위(--size)는 200에서 3000 사이로 적습니다. 표고 격자가 약 30m라 200m보다 좁으면 뜻이 없습니다.")
    return opts


def make(opts):
    try:
        grid, slopes = survey(opts["lat"], opts["lon"], opts["size"])
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, zlib.error) as e:
        die(f"표고 자료를 받지 못했습니다 ({e}).\n인터넷 연결을 확인하십시오. 받지 못한 채로 경사를 짐작해 적지 않습니다.")
    stats = summarize(grid, slopes)
    svg, scale = render(opts, grid, slopes, stats)
    out = Path(opts["out"])
    out.mkdir(parents=True, exist_ok=True)
    target = out / "경사참고도.svg"
    target.write_text(svg, encoding="utf-8")
    made = [target]
    browser = find_browser()
    if browser:
        made += export(svg, out / "경사참고도.pdf", out / "경사참고도.png", browser)
    print(f"경사 참고도 · 범위 {opts['size']:g}m · 축척 약 1/{scale:,} · A4 가로")
    for f in made:
        print(f"  {f}")
    print(f"  평균 경사 {stats['평균']:.1f}° ({stats['평균퍼센트']:.0f}%) · 가장 급한 칸 {stats['최대']:.1f}° · "
          f"{LIMIT_DEG}° 이상 {stats['기준이상']:.1f}% · 표고 {stats['최저표고']:.0f}~{stats['최고표고']:.0f}m")
    print("  참고용입니다. 격자가 약 30m라 좁은 땅의 경사는 현장에서 재야 하고, 평균경사도 조사서를 대신하지 못합니다.")


def main():
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "make":
        make(parse(a[1:]))
    elif not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
    else:
        die(__doc__)


if __name__ == "__main__":
    main()
