"""geo.py — 브이월드 조회와 좌표 변환 (parcel.py, basemap.py가 함께 쓴다).

도면 좌표는 미터다. 원점(필지를 둘러싼 네모의 남서쪽 모서리)의 위도·경도와
1도가 몇 미터인지를 도면 파일의 '원점'에 적어 두고, 그것으로 경위도와 오간다.
"""
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DATA_API = os.environ.get("BARUCH_VWORLD_SERVER", "https://api.vworld.kr/req/data")
NED_API = "https://api.vworld.kr/ned/data"
TILE_API = "https://api.vworld.kr/req/wmts/1.0.0"
KEY_FILE = Path.home() / ".config" / "baruch" / "vworld_key"
AGENT = {"User-Agent": "baruch-drawing/1"}


class VworldError(Exception):
    """브이월드가 조회를 받지 않았을 때."""


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def read_key():
    key = os.environ.get("VWORLD_KEY", "").strip()
    if not key and KEY_FILE.exists():
        lines = KEY_FILE.read_text(encoding="utf-8").split()
        key = lines[0] if lines else ""
    if not re.fullmatch(r"[A-Za-z0-9-]{20,60}", key):
        die("브이월드 인증키가 없습니다.\n"
            "https://www.vworld.kr 에서 오픈API 인증키를 발급받아(무료) 환경변수 VWORLD_KEY에 넣거나 "
            f"{KEY_FILE} 파일에 한 줄로 적으십시오.\n"
            "키가 없으면 대지경계는 지적도 등본에서 읽어 직접 적고, 바탕 지도는 쓰지 않습니다.")
    return key


def fetch(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=timeout) as r:
        return r.read()


def features(layer, key, **filters):
    """2D데이터 API에서 도형 목록을 받는다. 없으면 빈 목록."""
    query = urllib.parse.urlencode({"service": "data", "request": "GetFeature", "data": layer, "format": "json",
                                    "crs": "EPSG:4326", "size": "1000", "key": key, **filters})
    body = json.loads(fetch(f"{DATA_API}?{query}").decode())["response"]
    if body.get("status") == "NOT_FOUND":
        return []
    if body.get("status") != "OK":
        err = body.get("error") or {}
        raise VworldError(f"{err.get('code', body.get('status'))} {err.get('text', '')}".strip())
    return body["result"]["featureCollection"]["features"]


def land_register(pnu, key):
    """토지대장·임야대장의 지목과 면적. 못 찾으면 None."""
    query = urllib.parse.urlencode({"key": key, "pnu": pnu, "format": "json", "numOfRows": "5", "pageNo": "1"})
    body = json.loads(fetch(f"{NED_API}/ladfrlList?{query}").decode())
    rows = (body.get("ladfrlVOList") or {}).get("ladfrlVOList") or []
    if not rows:
        return None
    row = rows[0]
    return {"대장": row.get("regstrSeCodeNm", "토지대장"), "지목": row.get("lndcgrCodeNm", ""),
            "면적": float(row["lndpclAr"]), "갱신일": row.get("lastUpdtDt", "")}


def degree_lengths(lat):
    """그 위도에서 위도 1도, 경도 1도의 길이(m)."""
    phi = math.radians(lat)
    return (111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi),
            111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi))


def make_origin(ring):
    """경위도 고리에서 원점(남서쪽 모서리)을 잡는다."""
    lats = [p[1] for p in ring]
    lons = [p[0] for p in ring]
    per_lat, per_lon = degree_lengths((min(lats) + max(lats)) / 2)
    return {"위도": min(lats), "경도": min(lons), "위도1도": per_lat, "경도1도": per_lon}


def to_local(origin, lon, lat):
    return (round((lon - origin["경도"]) * origin["경도1도"], 2), round((lat - origin["위도"]) * origin["위도1도"], 2))


def to_lonlat(origin, x, y):
    return (origin["경도"] + x / origin["경도1도"], origin["위도"] + y / origin["위도1도"])


def local_ring(origin, ring):
    pts = [to_local(origin, lon, lat) for lon, lat in ring]
    return pts[:-1] if len(pts) > 1 and pts[0] == pts[-1] else pts


def outer_rings(geometry):
    """도형의 바깥 고리들 (경위도)."""
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    return [poly[0] for poly in polygons], sum(len(poly) - 1 for poly in polygons)


def tile_of(lon, lat, zoom):
    n = 2 ** zoom
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tile_corner(x, y, zoom):
    """타일 번호의 북서쪽 모서리 경위도."""
    n = 2 ** zoom
    return (x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n)))))
