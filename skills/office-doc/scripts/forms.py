#!/usr/bin/env python3
"""관청 서식(별지 서식) 원본 파일을 국가법령정보센터(law.go.kr)에서 찾아 받는다.

표준 라이브러리만 쓴다. 인증키가 필요 없다. 보내는 것은 법령 이름과 서식 번호뿐이다.

  forms.py list "식품위생법 시행규칙"            그 법령의 서식 목록 (번호, 이름)
  forms.py list "식품위생법 시행규칙" 신고서      이름에 낱말이 든 서식만
  forms.py get  "식품위생법 시행규칙" 37         별지 제37호서식 원본(한글 파일)을 받는다
  forms.py get  "식품위생법 시행규칙" 41의2 --pdf  PDF로 받는다
  forms.py get  "…" 37 -o 업무/식당-영업신고/서식   받을 폴더 (기본: 지금 폴더의 서식/)
  forms.py get  "…" 별표1                       별표도 같은 방법으로 받는다

받은 파일 맨 위의 개정일을 읽어 지금 시행 중인 서식인지 확인한다. 법령 이름은
law.go.kr에 적힌 그대로 넣는다(예: "식품위생법 시행규칙"). 법원·등기소의 양식과
고시·훈령의 서식은 여기서 받을 수 없다.
"""
import argparse
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.law.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (baruch forms.py)"}


def die(msg):
    print("오류: " + msg, file=sys.stderr)
    sys.exit(1)


def fetch(url, data=None, raw=False):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=UA)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read()
                return (b, r.headers) if raw else b.decode("utf-8", "replace")
        except Exception as e:  # 잠깐 끊긴 것일 수 있어 두 번 더 해 본다
            err = e
            time.sleep(1.5 * (attempt + 1))
    die(f"law.go.kr에 닿지 못했습니다 ({err}). 잠시 뒤 다시 하거나 누리집에서 직접 받으십시오.")


def parse_no(text):
    """'37', '41의2', '서식 37', '별지 제41호의2서식', '별표1' → (종류, 번호, 가지번호)"""
    t = unicodedata.normalize("NFC", text).replace(" ", "")
    kind = "별표" if "별표" in t else "서식"
    m = re.search(r"(\d+)(?:호)?(?:의(\d+))?", t)
    if not m:
        die(f"서식 번호를 읽지 못했습니다: {text}")
    return kind, int(m.group(1)), int(m.group(2) or 0)


def entry(law, key):
    """법령 이름과 '서식37' 같은 열쇠로 그 쪽을 열어 (bylSeq, lsiSeq)를 얻는다."""
    s = fetch(BASE + "/" + urllib.parse.quote(f"법령별표서식/({law},{key})"))
    b = re.search(r'id="bylSeq"[^>]*value="(\d+)"', s)
    l = re.search(r'id="lsiSeq"[^>]*value="(\d+)"', s)
    return (b.group(1), l.group(1)) if b and l else (None, None)


def catalog(law):
    """그 법령의 별표·서식 전체. [(bylSeq, 종류, 번호, 가지번호, 시행일, 이름)], 법령 표시, lsiSeq"""
    byl, lsi = entry(law, "")
    if not byl:
        byl, lsi = entry(law, "서식1")
    if not byl:
        die(f"'{law}'에서 별표·서식을 찾지 못했습니다. 법령 이름을 law.go.kr에 적힌 그대로 넣었는지 보십시오 "
            "(시행규칙인지 시행령인지, 띄어쓰기). 서식이 없는 법령일 수도 있습니다.")
    s = fetch(BASE + "/LSW/lsBylInfoR.do", {"bylSeq": byl, "lsiSeq": lsi})
    head = re.search(r'ast_tit">([^<]*)<br />\s*<span class="c1">([^<]*)', s)
    title = (head.group(1).strip() + " " + head.group(2).strip()) if head else law
    rows = []
    for val, text in re.findall(r'<option value="([^"]+)"[^>]*>([^<]*)</option>', s):
        p = val.split(",")
        if len(p) < 5:
            continue
        kind = "서식" if p[3].endswith("2") else "별표"
        name = re.sub(r"^\[[^\]]*\]\s*", "", text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")).strip()
        rows.append((p[0], kind, int(p[1]), int(p[2]), p[4], name))
    return rows, title, lsi


def label(kind, no, br):
    if kind == "서식":
        return f"별지 제{no}호" + (f"의{br}" if br else "") + "서식"
    return f"별표 {no}" + (f"의{br}" if br else "")


def cmd_list(a):
    rows, title, _ = catalog(a.law)
    word = unicodedata.normalize("NFC", a.word) if a.word else None
    print(title)
    n = 0
    for _, kind, no, br, _, name in rows:
        if kind != "서식" and not a.all:
            continue
        if "삭제" in name[:4]:
            continue
        if word and word not in name:
            continue
        print(f"  {label(kind, no, br)}  {name}")
        n += 1
    print(f"({n}건. 받기: forms.py get \"{a.law}\" 번호)")


def cmd_get(a):
    kind, no, br = parse_no(a.no)
    rows, title, lsi = catalog(a.law)
    hit = [r for r in rows if r[1] == kind and r[2] == no and r[3] == br]
    if not hit:
        die(f"{title}에 {label(kind, no, br)}이 없습니다. `forms.py list \"{a.law}\"`로 번호를 확인하십시오.")
    byl, _, _, _, efyd, name = hit[0]
    if "삭제" in name[:4]:
        die(f"{label(kind, no, br)}은 삭제된 서식입니다 ({name}).")
    s = fetch(BASE + "/LSW/lsBylContentsInfoR.do",
              {"bylSeq": byl, "lsiSeq": lsi, "bylNo": f"{no:04d}", "bylBrNo": f"{br:02d}", "bylEfYd": efyd})
    han = re.search(r'id="hanFlSeq"[^>]*value="(\d+)"', s)
    pdf = re.search(r'id="pdfFlSeq"[^>]*value="(\d+)"', s)
    want = pdf if a.pdf else han
    if not want:
        other = han if a.pdf else pdf
        if not other:
            die("이 서식은 받을 파일이 없습니다. 관청 누리집에서 받으십시오.")
        print(("PDF" if a.pdf else "한글") + " 파일이 없어 " + ("한글" if a.pdf else "PDF") + " 파일로 받습니다.")
        want, a.pdf = other, not a.pdf
    data, headers = fetch(BASE + "/LSW/flDownload.do?flSeq=" + want.group(1), raw=True)
    ext = ".pdf" if a.pdf else ".hwp"
    cd = headers.get("Content-Disposition", "")
    m = re.search(r'filename="?([^";]+)', cd)
    if m:
        real = urllib.parse.unquote(m.group(1))
        if "." in real:
            ext = "." + real.rsplit(".", 1)[1].lower()
    if data[:5] == b"%PDF-":
        ext = ".pdf"
    elif data[:2] == b"PK":
        ext = ".hwpx" if ext not in (".hwpx", ".zip", ".odt") else ext
    elif data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" and len(data) < 2000:
        die("받은 것이 서식 파일이 아닙니다. 누리집에서 직접 받으십시오.")
    safe = re.sub(r'[\\/:*?"<>|]', "", name).strip()[:60]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / unicodedata.normalize("NFC", f"{a.law} {label(kind, no, br)} {safe}{ext}")
    if path.exists() and not a.force:
        die(f"이미 있습니다: {path}\n신청인이 적던 파일일 수 있으니 확인한 뒤 --force로 다시 받으십시오.")
    path.write_bytes(data)
    print(f"받았습니다: {path}")
    print(f"  {title}")
    print(f"  {label(kind, no, br)} {name} · 서식 시행일 {efyd[:4]}-{efyd[4:6]}-{efyd[6:]} · 받은 날 {time.strftime('%Y-%m-%d')}")
    print("  낼 때는 파일 맨 위의 개정일이 지금 시행 중인 것과 같은지 확인하십시오.")


def main():
    ap = argparse.ArgumentParser(description="관청 서식 원본을 law.go.kr에서 찾아 받는다")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="법령의 서식 목록")
    p.add_argument("law")
    p.add_argument("word", nargs="?")
    p.add_argument("--all", action="store_true", help="별표도 함께")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("get", help="서식 원본 받기")
    p.add_argument("law")
    p.add_argument("no")
    p.add_argument("-o", "--out", default="서식")
    p.add_argument("--pdf", action="store_true")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_get)
    a = ap.parse_args()
    a.law = unicodedata.normalize("NFC", a.law).strip()
    a.fn(a)


if __name__ == "__main__":
    main()
