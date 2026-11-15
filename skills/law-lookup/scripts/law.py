#!/usr/bin/env python3
"""바룩 법령 조회 도구.

law-go-kr-obsidian(대한민국 법령 옵시디언 볼트, CC0)을 내려받아
법령 이름 찾기와 조문 뽑기를 한다. 표준 라이브러리만 쓴다.

  law.py setup                 법령 저장소 내려받기 또는 최신으로 갱신 (update 도 같다. 7일마다 자동 갱신)
  law.py where                 법령 저장소 위치와 기준일
  law.py find 키워드 [키워드]   법령 이름 찾기 (모든 키워드를 포함)
  law.py meta 법령명            법령별 파일 목록과 공포·시행일
  law.py toc 법령명 [파일]      조문 제목 목록
  law.py art 법령명 조 [파일]   조문 본문 (예: art 민법 32 / art 법인세법 39 시행령 / art 법인세법 공익법인등의범위 시행규칙)
  law.py grep 낱말 [법령명]     본문 검색 (머리말과 부칙은 뺀다)

현행 법령 (법제처 Open API를 감싼 공개 서버 mcp.gomdori.app/law — 인터넷 필요):
  law.py live search 법령명              현행 법령 찾기 (MST, 공포일, 시행일)
  law.py live art 법령명 제32조          현행 조문. 가지번호도 그대로 (제18조의3)
  law.py live art 법령명 제32조 20240101  그날 시행 중이던 조문
  law.py live arts 법령명 제32조 제33조 제49조   한 법령의 여러 조문을 한 번에 (서버 호출을 줄인다)
  law.py live annex 법령명 [별표번호]     별표·서식
  law.py live call 도구이름 '{"인자":"값"}'  그 밖의 도구 (live tools 로 목록)

인증키: 환경변수 LAW_OC 가 있으면 본인 한도로, 없으면 공용 한도로 조회한다.
"""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

REPO = "https://github.com/moomoogrange/law-go-kr-obsidian.git"
HOME = Path(os.environ.get("BARUCH_LAW_DIR", Path.home() / ".local/share/baruch/law-go-kr-obsidian"))
ORDER = ["법률", "시행령", "시행규칙"]
LIVE = os.environ.get("BARUCH_LAW_SERVER", "https://mcp.gomdori.app/law")
STALE_DAYS = 7


def nfc(s):
    return unicodedata.normalize("NFC", s)


def squash(s):
    """띄어쓰기와 가운뎃점 차이를 없앤 비교용 문자열."""
    return re.sub(r"[\s·ㆍ․‧]", "", nfc(s))


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def refresh():
    """내려받은 지 오래됐으면 조용히 최신으로 맞춘다. 실패해도 조회는 계속한다."""
    mark = HOME / ".git" / "FETCH_HEAD"
    try:
        ref = mark if mark.exists() else HOME / ".git" / "HEAD"
        if not ref.exists() or time.time() - ref.stat().st_mtime < STALE_DAYS * 86400:
            return
        subprocess.run(["git", "-C", str(HOME), "pull", "--ff-only", "--quiet"],
                       timeout=60, capture_output=True, check=False)
        mark.touch()
    except Exception:
        pass


_refreshed = False


def law_root():
    global _refreshed
    root = HOME / "법령"
    if not root.is_dir():
        die(f"법령 저장소가 없습니다: {HOME}\n먼저 실행하십시오: python3 {Path(__file__).resolve()} setup\n"
            "저장소 없이 현행 조문만 보려면: law.py live art 법령명 제○조")
    if not _refreshed:
        _refreshed = True
        refresh()
    return root


def setup():
    if (HOME / ".git").is_dir():
        subprocess.run(["git", "-C", str(HOME), "pull", "--ff-only", "--quiet"], check=False)
    else:
        HOME.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "--depth", "1", "--quiet", REPO, str(HOME)])
        if r.returncode != 0:
            die("내려받기에 실패했습니다. 인터넷 연결과 git 설치를 확인하십시오.")
    where()


def where():
    law_root()
    last = subprocess.run(["git", "-C", str(HOME), "log", "-1", "--format=%ad", "--date=short"],
                          capture_output=True, text=True).stdout.strip()
    print(f"위치: {HOME}")
    print(f"저장소 마지막 갱신: {last or '알 수 없음'}")
    print("주의: 이 날짜 뒤에 바뀐 법령은 반영되어 있지 않습니다. 서류에 쓰기 전에 `law.py live art 법령명 제○조`로 현행 조문을 확인하십시오.")


def all_laws():
    return sorted(p for p in law_root().iterdir() if p.is_dir())


def find(words):
    keys = [squash(w) for w in words]
    hits = [p for p in all_laws() if all(k in squash(p.name) for k in keys)]
    if not hits:
        die("찾지 못했습니다. 낱말을 줄이거나 grep으로 본문을 검색하십시오.")
    for p in hits:
        print(nfc(p.name))


def resolve(name):
    key = squash(name)
    laws = all_laws()
    exact = [p for p in laws if squash(p.name) == key]
    if exact:
        return exact[0]
    part = [p for p in laws if key in squash(p.name)]
    if len(part) == 1:
        return part[0]
    if not part:
        die(f"'{name}' 법령을 찾지 못했습니다. find로 이름을 먼저 확인하십시오.")
    die(f"'{name}'에 해당하는 법령이 {len(part)}건입니다. 이름을 더 정확히 적으십시오:\n" +
        "\n".join("  " + nfc(p.name) for p in part[:30]))


def rank(stem):
    """법률 → 시행령·대통령령 → 시행규칙·부령·규칙 순서."""
    stem = nfc(stem)
    if stem.startswith("법률"):
        return 0
    if stem.startswith("시행령") or "대통령령" in stem:
        return 1
    return 2


def files_of(law):
    fs = sorted(law.glob("*.md"), key=lambda f: (rank(f.stem), nfc(f.name)))
    if not fs:
        die(f"{nfc(law.name)}에 파일이 없습니다.")
    return fs


def pick(law, which):
    fs = files_of(law)
    if which is None:
        if len(fs) > 1:
            print(f"※ {nfc(law.name)}에 파일이 {len(fs)}개 있습니다: " + ", ".join(nfc(f.stem) for f in fs) +
                  f". 지금은 '{nfc(fs[0].stem)}'을 읽습니다. 다른 파일은 이름을 뒤에 붙이십시오.\n", file=sys.stderr)
        return fs[0]
    for f in fs:
        if squash(f.stem) == squash(which):
            return f
    die(f"'{which}' 파일이 없습니다. 있는 파일: " + ", ".join(nfc(f.stem) for f in fs))


def front(f):
    out = {}
    lines = f.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            m = re.match(r"^(제목|공포일자|시행일자|상태|출처|법령구분):\s*(.*)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def meta(name):
    law = resolve(name)
    print(nfc(law.name))
    for f in files_of(law):
        m = front(f)
        print(f"  {nfc(f.stem)}: 공포 {m.get('공포일자', '?')} / 시행 {m.get('시행일자', '?')} / {m.get('상태', '?')}")
        if m.get("출처"):
            print(f"    원문: {m['출처']}")
        print(f"    파일: {f}")


HEAD = re.compile(r"^#{2,6}\s+(제\d+조(?:의\d+)?)\b(.*)$")


def toc(name, which=None):
    f = pick(resolve(name), which)
    for line in f.read_text(encoding="utf-8").splitlines():
        m = HEAD.match(nfc(line))
        if m:
            print(m.group(1) + m.group(2))


def art(name, no, which=None):
    """조 번호 또는 제목 낱말로 조문을 뽑는다.

    이 저장소는 가지번호(제18조의3 등)를 제목에 '제18조'로만 적는다.
    그래서 같은 번호의 조문을 모두 보여 주고, 제목으로 가려 읽게 한다.
    """
    law = resolve(name)
    f = pick(law, which)
    no = nfc(no).replace(" ", "")
    m = re.match(r"^제?(\d+)조?(?:의(\d+))?$", no)
    want = f"제{m.group(1)}조" if m else None
    out, on, count = [], False, 0
    for line in f.read_text(encoding="utf-8").splitlines():
        line = nfc(line)
        h = HEAD.match(line)
        if h or re.match(r"^#{1,6}\s", line):
            if want:
                on = bool(h and h.group(1).split("의")[0] == want)
            else:
                on = bool(h and no in squash(h.group(2)))
            count += on
        if on:
            out.append(line)
    if not out:
        die(f"{nfc(law.name)} {nfc(f.stem)}에서 '{no}'를 찾지 못했습니다. toc로 조문 목록을 확인하십시오.")
    md = front(f)
    print(f"[{md.get('제목', nfc(law.name))} · {nfc(f.stem)} · 시행 {md.get('시행일자', '?')}]")
    if count > 1 or (m and m.group(2)):
        print(f"※ 같은 번호의 조문이 {count}개 있습니다. 이 저장소는 가지번호(의2, 의3)를 제목에 적지 않으니 "
              "제목을 보고 맞는 조문을 고르고, 정확한 조 번호는 아래 원문에서 확인하십시오.\n")
    print("\n".join(out).rstrip())
    if md.get("출처"):
        print(f"\n원문 확인: {md['출처']}")


def grep(word, name=None):
    targets = [resolve(name)] if name else all_laws()
    key, n = nfc(word), 0
    for law in targets:
        for f in files_of(law) if name else sorted(law.glob("*.md")):
            cur, front_n, body = "", 0, True
            for line in f.read_text(encoding="utf-8").splitlines():
                line = nfc(line)
                if line.strip() == "---" and front_n < 2:
                    front_n += 1
                    continue
                if front_n == 1:
                    continue  # 머리말
                if re.match(r"^#{1,6}\s*부\s*칙", line):
                    body = False  # 부칙(타법개정 포함)부터는 건너뛴다
                if not body:
                    continue
                h = HEAD.match(line)
                if h:
                    cur = h.group(1)
                if key in line:
                    print(f"{nfc(law.name)}/{nfc(f.stem)} {cur}: {line.strip()[:160]}")
                    n += 1
                    if n >= 80:
                        print("… 80건에서 멈췄습니다. 법령명을 붙여 범위를 좁히십시오.")
                        return
    if n == 0:
        die("찾지 못했습니다.")


# ── 현행 법령 (공개 서버) ────────────────────────────────────────────

def _post(body, sid=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if sid:
        h["mcp-session-id"] = sid
    oc = os.environ.get("LAW_OC", "").strip()
    if oc:
        h["apikey"] = oc
    req = urllib.request.Request(LIVE, json.dumps(body).encode(), h)
    with urllib.request.urlopen(req, timeout=120) as r:
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
        "clientInfo": {"name": "baruch-law", "version": "1"}}})
    try:
        _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    except Exception:
        pass
    return sid


def live_call(tool, args, sid=None):
    sid = sid or _session()
    d, _ = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": tool, "arguments": args}}, sid)
    r = (d or {}).get("result", d or {})
    texts = [c["text"] for c in r.get("content", []) if c.get("type") == "text"]
    return "\n".join(texts) if texts else json.dumps(r, ensure_ascii=False)[:4000]


def live_find(name, sid):
    """법령명으로 현행 법령의 MST를 찾는다. 정확히 같은 이름을 먼저 고른다."""
    txt = live_call("search_law", {"query": name, "display": 10}, sid)
    best, key = None, squash(name)
    for m in re.finditer(r"^\s*\d+\.\s*(.+?)\s*\[(.+?)\]\s*\n(?:.*\n){0,2}?.*MST:\s*(\d+)", txt, re.M):
        title, state, mst = m.group(1), m.group(2), m.group(3)
        if squash(title) == key:
            return mst, title, txt
        best = best or (mst, title, txt)
    if not best:
        die(f"'{name}'을 현행 법령에서 찾지 못했습니다.\n{txt[:600]}")
    return best


def live(rest):
    if not rest:
        die(__doc__)
    sub, a = rest[0], rest[1:]
    try:
        if sub == "tools":
            sid = _session()
            d, _ = _post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, sid)
            for t in d["result"]["tools"]:
                print(t["name"], "—", t["description"][:110].replace("\n", " "))
        elif sub == "search" and a:
            print(live_call("search_law", {"query": " ".join(a), "display": 10}))
        elif sub == "art" and len(a) >= 2:
            sid = _session()
            mst, title, _ = live_find(a[0], sid)
            args = {"mst": mst, "jo": a[1] if a[1].startswith("제") else f"제{a[1]}조".replace("조조", "조")}
            if len(a) >= 3:
                args["efYd"] = a[2]
            print(f"[현행 조회 · {title} · MST {mst}" + (f" · 기준일 {a[2]}" if len(a) >= 3 else "") + "]")
            print(live_call("get_law_text", args, sid))
        elif sub == "arts" and len(a) >= 2:
            sid = _session()
            mst, title, _ = live_find(a[0], sid)
            arts = [x if x.startswith("제") else f"제{x}조" for x in a[1:]]
            print(f"[현행 조회 · {title} · MST {mst} · {len(arts)}개 조문]")
            print(live_call("execute_tool", {"tool_name": "get_batch_articles",
                                             "params": {"mst": mst, "articles": arts}}, sid))
        elif sub == "annex" and a:
            args = {"lawName": a[0]}
            if len(a) >= 2:
                args["annexNo"] = a[1]
            print(live_call("get_annexes", args))
        elif sub == "call" and a:
            print(live_call(a[0], json.loads(a[1]) if len(a) >= 2 else {}))
        else:
            die(__doc__)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        die(f"현행 법령 서버에 닿지 못했습니다 ({e}).\n"
            "인터넷 연결을 확인하거나, 내려받은 저장소로 조회하십시오 (law.py art …). "
            "저장소로 읽은 조문은 law.go.kr에서 현행 여부를 확인해야 합니다.")


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, rest = a[0], a[1:]
    try:
        if cmd in ("setup", "update"):
            setup()
        elif cmd == "live":
            live(rest)
        elif cmd == "where":
            where()
        elif cmd == "find" and rest:
            find(rest)
        elif cmd == "meta" and len(rest) == 1:
            meta(rest[0])
        elif cmd == "toc" and 1 <= len(rest) <= 2:
            toc(*rest)
        elif cmd == "art" and 2 <= len(rest) <= 3:
            art(*rest)
        elif cmd == "grep" and 1 <= len(rest) <= 2:
            grep(*rest)
        else:
            die(__doc__)
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
