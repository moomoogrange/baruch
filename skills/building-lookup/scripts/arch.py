#!/usr/bin/env python3
"""arch.py — 건축물대장·건축인허가 조회 (바룩 building-lookup 스킬)

국토교통부 건축HUB(공공데이터포털)를 감싼 공개 서버 mcp.gomdori.app/archhub 를 부른다.
파이썬 3만 있으면 된다. 인터넷이 필요하다. 인증키는 필요 없다.

  arch.py region  광진구 자양동                 법정동 코드 찾기
  arch.py profile 광진구 자양동 2-2             건축물 종합카드 (용도지역, 주용도, 구조, 면적, 사용승인일, 정화조)
  arch.py history 광진구 자양동 2-2             필지 연혁 (허가 → 착공 → 사용승인, 철거, 가설건축물)
  arch.py floors  광진구 자양동 2-2             층별 용도와 면적
  arch.py temp    광진구 자양동 2-2             가설건축물과 존치기간 만료일 (번지를 빼면 동 전체)
  arch.py raw ledger 표제부 광진구 자양동 2-2    대장 원본 행 (ledger 건축물대장 · permit 건축인허가 · housing 주택인허가)
  arch.py tools                                쓸 수 있는 도구 목록
  arch.py call 도구이름 '{"인자":"값"}'          도구를 직접 부르기

주소는 시·군·구, 법정동(읍·면·리), 번지 순으로 띄어 쓴다. 번지는 "2-2"나 "680"처럼 적는다.
사람 이름, 상호, 사연은 넣지 않는다. 주소만 보낸다.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

LIVE = os.environ.get("BARUCH_ARCH_SERVER", "https://mcp.gomdori.app/archhub")
BUNJI = re.compile(r"^(\d{1,4})(?:-(\d{1,4}))?(?:번지)?$")
ROW = re.compile(r"^\s*(.+?)\s+(\d{5})\s+(\d{5})(?:\s+(\S.*))?$")
PARCEL_TOOLS = {
    "profile": "building_profile",
    "history": "parcel_history",
    "floors": "building_floors",
    "temp": "temp_buildings",
}
NEEDS_BUNJI = ("profile", "history", "floors")


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def _post(body, sid=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if sid:
        headers["mcp-session-id"] = sid
    req = urllib.request.Request(LIVE, json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        sid = r.headers.get("mcp-session-id") or sid
        txt = r.read().decode()
    out = None
    for line in txt.splitlines():
        if line.startswith("data: "):
            out = json.loads(line[6:])
    if out is None and txt.strip().startswith("{"):
        out = json.loads(txt)
    return out, sid


def _session():
    _, sid = _post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "baruch-arch", "version": "1"}}})
    try:
        _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    except Exception:
        pass
    return sid


def call(tool, args, sid=None):
    """도구를 부르고 (글, 오류 여부)를 돌려준다."""
    sid = sid or _session()
    d, _ = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": tool, "arguments": args}}, sid)
    d = d or {}
    if "error" in d:
        return json.dumps(d["error"], ensure_ascii=False), True
    r = d.get("result", d)
    texts = [c["text"] for c in r.get("content", []) if c.get("type") == "text"]
    text = "\n".join(texts) if texts else json.dumps(r, ensure_ascii=False)[:4000]
    return text, bool(r.get("isError"))


def show(tool, args, sid=None):
    text, failed = call(tool, args, sid)
    print(text)
    if failed:
        die("\n조회하지 못했습니다. 이 결과로 건물 사실을 적지 않습니다. 건축물대장을 직접 떼어 확인하십시오.")


def split_address(words):
    """낱말 목록을 (지역 낱말, 본번, 부번)으로 나눈다."""
    region, bun, ji = [], "", ""
    for w in words:
        m = BUNJI.fullmatch(w)
        if m and not bun:
            bun, ji = m.group(1), m.group(2) or ""
        else:
            region.append(w)
    return region, bun, ji


def resolve(words, sid):
    """주소 낱말에서 시군구 코드, 법정동 코드, 번지를 찾는다. 하나로 정해지지 않으면 멈춘다."""
    region, bun, ji = split_address(words)
    if not region:
        die("동 이름이 없습니다. 예: arch.py profile 광진구 자양동 2-2")
    text, failed = call("find_region", {"keyword": " ".join(region), "limit": 30}, sid)
    if failed or "[NOT_FOUND]" in text:
        die(text + "\n\n지역을 찾지 못했습니다. 행정동(자양1동)이 아니라 법정동(자양동) 이름으로 다시 찾으십시오.")
    rows = []
    for line in text.splitlines():
        m = ROW.match(line)
        if m and m.group(3) != "00000":
            rows.append((m.group(1).strip(), m.group(2), m.group(3)))
    if not rows:
        die(text + "\n\n동 단위 코드를 찾지 못했습니다. 읍·면·동 이름까지 적으십시오.")
    if len(rows) > 1:
        names = "\n".join(f"  {name}" for name, _, _ in rows)
        die(f"같은 이름의 지역이 {len(rows)}곳입니다. 시·군·구(리 단위면 읍·면과 리)까지 적어 하나로 좁히십시오.\n{names}")
    name, sigungu, bdong = rows[0]
    return {"name": " ".join(name.split()), "sigungu_code": sigungu, "bdong_code": bdong, "bun": bun, "ji": ji}


def parcel_args(place, need_bunji):
    if need_bunji and not place["bun"]:
        die("번지가 필요합니다. 예: 광진구 자양동 2-2")
    args = {"sigungu_code": place["sigungu_code"], "bdong_code": place["bdong_code"]}
    if place["bun"]:
        args["bun"] = place["bun"]
    if place["ji"]:
        args["ji"] = place["ji"]
    return args


def header(place, what):
    bunji = place["bun"] + (f"-{place['ji']}" if place["ji"] else "")
    where = f"{place['name']} {bunji}".strip()
    print(f"[건축HUB 조회 · {what} · {where} · 시군구 {place['sigungu_code']} 법정동 {place['bdong_code']}]")


def run(cmd, rest):
    if cmd == "tools":
        sid = _session()
        d, _ = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, sid)
        for t in d["result"]["tools"]:
            print(t["name"], "—", t["description"][:110].replace("\n", " "))
    elif cmd == "region" and rest:
        region, _, _ = split_address(rest)
        show("find_region", {"keyword": " ".join(region or rest), "limit": 30})
    elif cmd in PARCEL_TOOLS and rest:
        sid = _session()
        place = resolve(rest, sid)
        header(place, PARCEL_TOOLS[cmd])
        show(PARCEL_TOOLS[cmd], parcel_args(place, cmd in NEEDS_BUNJI), sid)
    elif cmd == "raw" and len(rest) >= 3:
        sid = _session()
        place = resolve(rest[2:], sid)
        header(place, f"{rest[0]} {rest[1]}")
        args = parcel_args(place, False)
        show("building_data", {"kind": rest[0], "type_name": rest[1], "max_rows": 100, **args}, sid)
    elif cmd == "call" and rest:
        show(rest[0], json.loads(rest[1]) if len(rest) >= 2 else {})
    else:
        die(__doc__)


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    try:
        run(a[0], a[1:])
    except json.JSONDecodeError as e:
        die(f"인자를 읽지 못했습니다 ({e}). call 뒤의 인자는 JSON으로 적습니다.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        die(f"건축HUB 조회 서버에 닿지 못했습니다 ({e}).\n"
            "인터넷 연결을 확인하십시오. 조회하지 못한 건물 사실은 적지 않고, "
            "정부24나 세움터에서 건축물대장을 떼어 확인하십시오.")
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
