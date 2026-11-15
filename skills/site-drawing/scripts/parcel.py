#!/usr/bin/env python3
"""parcel.py — 지번으로 필지 경계와 대장 면적 받기 (바룩 site-drawing 스킬)

브이월드(국토교통부 공간정보 오픈플랫폼)에서 필지 경계(연속지적도), 토지대장·임야대장의 지목과 면적,
그 필지에 있는 건물의 윤곽과 건축물대장 건축면적을 받아 도면에 쓸 미터 좌표로 바꾼다.
본인 인증키가 필요하다.

  parcel.py show 광진구 자양동 2-2                 경계, 대장 면적, 건물, 가운데 좌표 보기
  parcel.py show 평창군 대관령면 횡계리 산 1-1      산 번지는 '산'을 띄어 쓰거나 붙여 쓴다
  parcel.py into 배치도.json 광진구 자양동 2-2      도면 파일에 대지경계·대지면적·주소·방위·원점을 채우기
  parcel.py into 배치도.json 광진구 자양동 2-2 --buildings
                                                  그 필지의 기존 건물 윤곽도 함께 넣기

인증키: 환경변수 VWORLD_KEY, 없으면 ~/.config/baruch/vworld_key 파일의 첫 줄.
        https://www.vworld.kr 에 가입해 오픈API 인증키를 발급받는다 (무료, 개발키 6개월).
        서비스유형은 '기타', 활용API는 2D데이터·WMTS/TMS·국가중점(또는 전부)을 고른다.

좌표는 필지를 둘러싼 네모의 왼쪽 아래(남서쪽) 모서리를 [0, 0]으로 하고 x는 동쪽, y는 북쪽이다.
연속지적도와 건물 윤곽은 참고용이다. 경계를 확정하는 측량 자료로 쓸 수 없다.
"""
import json
import re
import sys
import urllib.error
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "building-lookup" / "scripts"))
from arch import _session, resolve  # noqa: E402
from draw import area, inside  # noqa: E402
from geo import VworldError, die, features, land_register, local_ring, make_origin, outer_rings, read_key  # noqa: E402

SOURCE = "브이월드 연속지적도"
BUILDING_SOURCE = "브이월드 GIS건물통합정보"
TOLERANCE = 0.02                               # 대장 면적과 지도에서 잰 넓이가 이보다 더 다르면 알린다


def split_mountain(words):
    """'산' 번지 표시를 떼어 낸다. (남은 낱말, 산 여부)"""
    rest, mountain = [], False
    for w in words:
        m = re.fullmatch(r"산(\d{1,4}(?:-\d{1,4})?(?:번지)?)?", w)
        if m:
            mountain = True
            rest += [m.group(1)] if m.group(1) else []
        else:
            rest.append(w)
    return rest, mountain


def make_pnu(place, mountain):
    if not place["bun"]:
        die("번지가 필요합니다. 예: 광진구 자양동 2-2")
    return (place["sigungu_code"] + place["bdong_code"] + ("2" if mountain else "1")
            + place["bun"].zfill(4) + (place["ji"] or "0").zfill(4))


def gap(measured, registered):
    """대장 면적에 견준 차이의 비율."""
    return abs(measured - registered) / registered if registered else 0.0


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def buildings_in(parcel_ring, origin, boundary, key):
    """필지 안에 가운데가 놓인 건물의 윤곽과 건축물대장 면적."""
    lons = [p[0] for p in parcel_ring]
    lats = [p[1] for p in parcel_ring]
    box = f"BOX({min(lons)},{min(lats)},{max(lons)},{max(lats)})"
    out = []
    for f in features("LT_C_BLDGINFO", key, geomFilter=box):
        rings, _ = outer_rings(f["geometry"])
        ring = max((local_ring(origin, r) for r in rings), key=area)
        centre = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
        if not inside(centre, boundary):
            continue
        p = f["properties"]
        day = str(p.get("useapr_day") or "")
        floors = f"지상 {p['grnd_flr']}층" if str(p.get("grnd_flr") or "0") not in ("0", "") else ""
        approved = f"사용승인 {day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) == 8 else ""
        out.append({"동": (p.get("dong_nm") or "").strip(), "꼭짓점": [list(pt) for pt in ring],
                    "대장면적": number(p.get("archarea")), "연면적": number(p.get("totalarea")),
                    "설명": " · ".join(v for v in (floors, approved) if v)})
    return sorted(out, key=lambda b: -area([tuple(pt) for pt in b["꼭짓점"]]))


def lookup(words):
    """주소 낱말로 필지를 찾아 도면에 쓸 값으로 돌려준다."""
    rest, mountain = split_mountain(words)
    place = resolve(rest, _session())
    key = read_key()
    pnu = make_pnu(place, mountain)
    found = features("LP_PA_CBND_BUBUN", key, attrFilter=f"pnu:=:{pnu}")
    if not found:
        die(f"이 지번의 필지를 찾지 못했습니다 (PNU {pnu}).\n"
            "지번과 '산' 여부를 확인하십시오. 찾지 못한 경계를 짐작해 그리지 않습니다.")
    props = found[0]["properties"]
    rings, holes = outer_rings(found[0]["geometry"])
    ring = max(rings, key=lambda r: area(local_ring(make_origin(r), r)))
    origin = make_origin(ring)
    boundary = local_ring(origin, ring)
    return {"주소": props.get("addr", ""), "지번지목": props.get("jibun", ""), "pnu": pnu, "원점": origin,
            "경계": [list(p) for p in boundary], "넓이": area(boundary), "조각": len(rings), "구멍": holes,
            "위도": sum(p[1] for p in ring) / len(ring), "경도": sum(p[0] for p in ring) / len(ring),
            "대장": land_register(pnu, key), "건물": buildings_in(ring, origin, boundary, key)}


def report_land(found):
    register = found["대장"]
    print(f"  지도 경계로 잰 넓이  {found['넓이']:,.1f}㎡ (꼭짓점 {len(found['경계'])}개)")
    if not register:
        print("  [살필 것] 토지대장·임야대장 면적을 받지 못했습니다. 대장을 떼어 면적을 직접 적으십시오.")
        return
    diff = gap(found["넓이"], register["면적"])
    print(f"  {register['대장']}  지목 {register['지목']} · 면적 {register['면적']:,.1f}㎡ (대장 갱신 {register['갱신일']})")
    print(f"  차이  {found['넓이'] - register['면적']:+,.1f}㎡ ({diff * 100:.1f}%)")
    if diff > TOLERANCE:
        print(f"  [살필 것] 지도 경계와 {register['대장']} 면적이 {diff * 100:.1f}% 다릅니다. 분할·합병이 지도에 늦게 반영됐거나 "
              "경계가 어긋난 것일 수 있습니다. 지적도 등본으로 경계를 확인하십시오. 도면의 대지면적에는 대장 면적을 씁니다.")


def report_buildings(found):
    if not found["건물"]:
        print("  건물  이 필지에서 건물 윤곽을 찾지 못했습니다 (건물이 없거나 지도에 올라 있지 않음).")
        return
    print(f"  건물 {len(found['건물'])}동 — 건축물대장 건축면적과 지도 윤곽으로 잰 넓이")
    for i, b in enumerate(found["건물"], 1):
        measured = area([tuple(p) for p in b["꼭짓점"]])
        name = b["동"] or f"건물 {i}"
        if not b["대장면적"]:
            print(f"    {name}: 지도 윤곽 {measured:,.1f}㎡ · 대장 건축면적 없음 {b['설명']}")
            continue
        diff = gap(measured, b["대장면적"])
        flag = "  [살필 것] 대장과 다름 — 증축·멸실이 반영 안 됐을 수 있음" if diff > TOLERANCE * 5 else ""
        print(f"    {name}: 대장 {b['대장면적']:,.2f}㎡ · 지도 윤곽 {measured:,.1f}㎡ ({diff * 100:.1f}% 차이) {b['설명']}{flag}")


def report(found):
    print(f"[{SOURCE} · 조회일 {date.today().isoformat()} · PNU {found['pnu']}]")
    print(f"  주소  {found['주소']}")
    print(f"  지번·지목  {found['지번지목']}")
    report_land(found)
    report_buildings(found)
    print(f"  가운데 좌표  위도 {found['위도']:.5f} 경도 {found['경도']:.5f}   (slope.py make {found['위도']:.5f} {found['경도']:.5f})")
    if found["조각"] > 1 or found["구멍"]:
        parts = [f"필지가 {found['조각']}조각입니다"] if found["조각"] > 1 else []
        parts += [f"필지 안쪽에 다른 필지가 {found['구멍']}곳 들어 있습니다"] if found["구멍"] else []
        print(f"  [살필 것] {' · '.join(parts)}. 가장 큰 바깥 경계만 썼습니다.")
    print("  연속지적도와 건물 윤곽은 참고용입니다. 경계를 확정하는 자료로 쓸 수 없고, 낼 때는 대장 등본으로 다시 맞춥니다.")


def as_drawing_buildings(found):
    out = []
    for i, b in enumerate(found["건물"], 1):
        entry = {"이름": b["동"] or f"기존 건물 {i}", "구분": "기존", "꼭짓점": b["꼭짓점"], "출처": BUILDING_SOURCE}
        entry.update({"대장면적": b["대장면적"]} if b["대장면적"] else {})
        entry.update({"설명": b["설명"]} if b["설명"] else {})
        out.append(entry)
    return out


def merge(path, found, with_buildings):
    """도면 파일에 대지경계, 대지면적, 주소, 방위, 원점, 위치 근거를 채운 새 내용을 쓴다."""
    target = Path(path)
    try:
        spec = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    except json.JSONDecodeError as e:
        die(f"도면 파일을 읽지 못했습니다: {path} ({e})")
    today = date.today().isoformat()
    note = f"대지경계선은 {SOURCE}(조회일 {today})에서 받은 참고용 경계"
    basis = str(spec.get("위치근거", "")).strip()
    merged = {**spec, "주소": found["주소"] or spec.get("주소", ""), "방위": "위", "대지경계": found["경계"],
              "원점": found["원점"],
              "위치근거": basis if SOURCE in basis else " · ".join(v for v in (basis, note) if v)}
    if found["대장"]:
        merged = {**merged, "대지면적": found["대장"]["면적"], "대지면적출처": f"{found['대장']['대장']} {found['대장']['갱신일']}"}
    if with_buildings:
        kept = [b for b in spec.get("건물", []) if b.get("출처") != BUILDING_SOURCE]
        merged = {**merged, "건물": as_drawing_buildings(found) + kept}
    target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    filled = "대지경계, 대지면적(대장), 주소, 방위(위쪽이 북), 원점" if found["대장"] else "대지경계, 주소, 방위(위쪽이 북), 원점"
    print(f"  {target} 에 {filled}을 넣었습니다." + (f" 기존 건물 {len(found['건물'])}동의 윤곽도 넣었습니다." if with_buildings else ""))
    print("  건물의 위치는 이 좌표로 적습니다: 필지를 둘러싼 네모의 남서쪽 모서리가 [0, 0], x는 동쪽, y는 북쪽(미터).")
    if spec.get("방위") not in (None, "위", 0):
        print("  [살필 것] 방위를 '위'로 바꿨습니다. 이미 적어 둔 건물 위치가 있으면 새 좌표에 맞게 다시 적으십시오.")


def main():
    a = [x for x in sys.argv[1:] if x != "--buildings"]
    with_buildings = "--buildings" in sys.argv[1:]
    try:
        if len(a) >= 3 and a[0] == "show":
            report(lookup(a[1:]))
        elif len(a) >= 4 and a[0] == "into":
            found = lookup(a[2:])
            report(found)
            merge(a[1], found, with_buildings)
        elif not a or a[0] in ("-h", "--help", "help"):
            print(__doc__)
        else:
            die(__doc__)
    except VworldError as e:
        die(f"브이월드가 조회를 받지 않았습니다: {e}\n"
            "인증키가 맞는지, 발급할 때 2D데이터 API와 국가중점 API를 골랐는지, 유효기간이 지나지 않았는지 확인하십시오.")
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, ValueError) as e:
        die(f"필지 정보를 받지 못했습니다 ({e}).\n인터넷 연결을 확인하십시오. 받지 못한 경계와 면적을 짐작해 적지 않습니다.")


if __name__ == "__main__":
    main()
