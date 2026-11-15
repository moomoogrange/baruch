"""basemap.py — 도면 바탕에 까는 항공사진·지도·지적도 (브이월드).

도면 파일의 '바탕'에 적힌 것을 받아 SVG 조각으로 돌려준다. '원점'(parcel.py into가 넣어 준다)과
본인 브이월드 인증키가 있어야 한다.
"""
import base64
import math
from datetime import date

from geo import TILE_API, features, fetch, outer_rings, read_key, tile_corner, tile_of, to_local, to_lonlat

TILE_LAYERS = {"항공사진": ("Satellite", "jpeg"), "지도": ("Base", "png")}
KINDS = ("항공사진", "지도", "지적도")
MAX_ZOOM = 19
MAX_TILES = 48
PIXELS_PER_MM = 8                               # 인쇄했을 때 사진이 뭉개지지 않을 만큼


def kinds_of(spec):
    value = spec.get("바탕")
    return [value] if isinstance(value, str) else list(value or [])


def world_box(view, box_mm):
    """종이 위 네모(mm)가 덮는 도면 좌표(미터) 범위."""
    x, y, w, h = box_mm
    left = view["minx"] + (x - view["ox"]) / view["s"]
    top = view["maxy"] - (y - view["oy"]) / view["s"]
    return left, top - h / view["s"], left + w / view["s"], top


def pick_zoom(origin, view, box):
    metres_per_pixel = 1 / (view["s"] * PIXELS_PER_MM)
    lat = origin["위도"]
    zoom = min(MAX_ZOOM, math.ceil(math.log2(156543.03 * math.cos(math.radians(lat)) / metres_per_pixel)))
    while zoom > 10:
        (x0, y0), (x1, y1) = tile_range(origin, box, zoom)
        if (x1 - x0 + 1) * (y1 - y0 + 1) <= MAX_TILES:
            break
        zoom -= 1
    return zoom


def tile_range(origin, box, zoom):
    west, south = to_lonlat(origin, box[0], box[1])
    east, north = to_lonlat(origin, box[2], box[3])
    x0, y0 = tile_of(west, north, zoom)
    x1, y1 = tile_of(east, south, zoom)
    return (int(x0), int(y0)), (int(x1), int(y1))


def tile_images(kind, origin, view, box, key, place):
    """바탕 타일을 받아 제자리에 놓은 <image> 목록."""
    layer, ext = TILE_LAYERS[kind]
    zoom = pick_zoom(origin, view, box)
    (x0, y0), (x1, y1) = tile_range(origin, box, zoom)
    mime = "image/jpeg" if ext == "jpeg" else "image/png"
    out = []
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            data = fetch(f"{TILE_API}/{key}/{layer}/{zoom}/{ty}/{tx}.{ext}")
            west, north = tile_corner(tx, ty, zoom)
            east, south = tile_corner(tx + 1, ty + 1, zoom)
            left, top = place(to_local(origin, west, north))
            right, bottom = place(to_local(origin, east, south))
            out.append(f'<image x="{left:.3f}" y="{top:.3f}" width="{right - left + 0.03:.3f}" height="{bottom - top + 0.03:.3f}" '
                       f'preserveAspectRatio="none" href="data:{mime};base64,{base64.b64encode(data).decode()}"/>')
    opacity = 0.85 if kind == "항공사진" else 0.7
    return [f'<g opacity="{opacity}">'] + out + ["</g>"]


def cadastral_lines(origin, view, box, key, place, on_photo):
    """둘레 필지의 경계선과 지번."""
    west, south = to_lonlat(origin, box[0], box[1])
    east, north = to_lonlat(origin, box[2], box[3])
    found = features("LP_PA_CBND_BUBUN", key, geomFilter=f"BOX({west},{south},{east},{north})")
    colour, width = ("#FFFFFF", 0.3) if on_photo else ("#8A8A8A", 0.18)
    out = []
    for f in found:
        rings, _ = outer_rings(f["geometry"])
        for ring in rings:
            pts = [place(to_local(origin, lon, lat)) for lon, lat in ring]
            path = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
            out.append(f'<polygon points="{path}" fill="none" stroke="{colour}" stroke-width="{width}"/>')
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            label = "".join(str(f["properties"].get("jibun", "")).split())
            if label and max(xs) - min(xs) > len(label) * 1.6 and max(ys) - min(ys) > 3:
                halo = ' style="paint-order:stroke;stroke:#fff;stroke-width:0.7px"' if on_photo else ""
                out.append(f'<text x="{(min(xs) + max(xs)) / 2:.2f}" y="{(min(ys) + max(ys)) / 2 + 0.7:.2f}" font-size="1.9" '
                           f'text-anchor="middle" fill="{"#222" if on_photo else "#555"}" font-family="sans-serif"{halo}>{label}</text>')
    return out, len(found)


def background(spec, view, box_mm, place):
    """(바탕 SVG 조각, 주기에 넣을 말, 글자에 흰 테를 두를지)를 돌려준다."""
    kinds = kinds_of(spec)
    origin = spec["원점"]
    key = read_key()
    box = world_box(view, box_mm)
    out = []
    photo = "항공사진" in kinds
    for kind in (k for k in ("항공사진", "지도") if k in kinds):
        out += tile_images(kind, origin, view, box, key, place)
    if "지적도" in kinds:
        lines, count = cadastral_lines(origin, view, box, key, place, photo)
        out += lines
        if count >= 1000:
            out.append("<!-- 필지가 1000개를 넘어 일부만 그렸다 -->")
    names = " · ".join("연속지적도" if k == "지적도" else k for k in kinds)
    note = f"바탕: 브이월드 {names} (국토교통부, 조회일 {date.today().isoformat()}). 참고용이며 실제 경계와 어긋날 수 있음"
    return out, [note], photo or "지도" in kinds
