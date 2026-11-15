#!/usr/bin/env python3
"""바룩 법령 조회 도구.

law-go-kr-obsidian(대한민국 법령 옵시디언 볼트, CC0)을 내려받아
법령 이름 찾기와 조문 뽑기를 한다. 표준 라이브러리만 쓴다.

  law.py setup                 법령 저장소 내려받기 또는 최신으로 갱신
  law.py where                 법령 저장소 위치와 기준일
  law.py find 키워드 [키워드]   법령 이름 찾기 (모든 키워드를 포함)
  law.py meta 법령명            법령별 파일 목록과 공포·시행일
  law.py toc 법령명 [파일]      조문 제목 목록
  law.py art 법령명 조 [파일]   조문 본문 (예: art 민법 32 / art 법인세법 39 시행령 / art 법인세법 공익법인등의범위 시행규칙)
  law.py grep 낱말 [법령명]     본문 검색
"""
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

REPO = "https://github.com/moomoogrange/law-go-kr-obsidian.git"
HOME = Path(os.environ.get("BARUCH_LAW_DIR", Path.home() / ".local/share/baruch/law-go-kr-obsidian"))
ORDER = ["법률", "시행령", "시행규칙"]


def nfc(s):
    return unicodedata.normalize("NFC", s)


def squash(s):
    """띄어쓰기와 가운뎃점 차이를 없앤 비교용 문자열."""
    return re.sub(r"[\s·ㆍ․‧]", "", nfc(s))


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def law_root():
    root = HOME / "법령"
    if not root.is_dir():
        die(f"법령 저장소가 없습니다: {HOME}\n먼저 실행하십시오: python3 {Path(__file__).resolve()} setup")
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
    print("주의: 이 날짜 뒤에 바뀐 법령은 반영되어 있지 않습니다. 제출 전 law.go.kr에서 현행 조문을 확인하십시오.")


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


def files_of(law):
    fs = sorted(law.glob("*.md"), key=lambda f: (ORDER.index(nfc(f.stem)) if nfc(f.stem) in ORDER else 9, nfc(f.name)))
    if not fs:
        die(f"{nfc(law.name)}에 파일이 없습니다.")
    return fs


def pick(law, which):
    fs = files_of(law)
    if which is None:
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
            cur = ""
            for line in f.read_text(encoding="utf-8").splitlines():
                line = nfc(line)
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


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, rest = a[0], a[1:]
    try:
        if cmd == "setup":
            setup()
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
