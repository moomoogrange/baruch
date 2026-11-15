#!/usr/bin/env python3
"""바룩 서류를 제출용 PDF로 바꾼다.

마크다운 초안(.md)을 A4 PDF로 만든다. 표준 라이브러리만 쓰고,
PDF 인쇄는 컴퓨터에 깔린 크롬·엣지·크로미움·브레이브를 화면 없이 돌려서 한다.

  make_pdf.py 파일.md [파일2.md …]         초안 PDF (쪽마다 '초안' 표시, 안내 문구 포함)
  make_pdf.py --final 파일.md …            제출용 PDF (안내 문구를 빼고, 빈칸이 남아 있으면 멈춘다)
  make_pdf.py --final -o 폴더 파일.md …     저장할 폴더 지정 (기본: 원본과 같은 폴더)
  make_pdf.py --final -n 03_정관 파일.md    파일 이름 지정 (확장자 없이, 파일이 하나일 때)
  make_pdf.py --check 파일.md …            PDF는 만들지 않고 남은 빈칸만 센다

제출용에서 빼는 것:
  - 문서 맨 위의 인용 블록(> 초안 … 같은 안내)
  - '<!-- 제출본에서 뺌 -->' 줄부터 끝까지, 또는 마지막 가로줄(---) 뒤의 안내 목록
  - 【40조】【지정】 같은 표시
제출용을 막는 것: {{…}}, [확인 필요…], [관청 확인…], [전문가 확인…], [조문 미확인…]
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOLES = [r"\{\{.*?\}\}", r"\[확인 필요[^\]]*\]", r"\[관청 확인[^\]]*\]", r"\[전문가 확인[^\]]*\]", r"\[조문 미확인[^\]]*\]"]
CUT = "<!-- 제출본에서 뺌 -->"

CSS = """
@page { size: A4; margin: 25mm 20mm 22mm 20mm; }
* { box-sizing: border-box; }
body { font-family: "AppleMyungjo", "Batang", "바탕", "Noto Serif CJK KR", "Noto Serif KR", "NanumMyeongjo", serif;
       font-size: 11.5pt; line-height: 1.75; color: #000; word-break: keep-all; overflow-wrap: anywhere; }
h1 { font-size: 18pt; text-align: center; margin: 0 0 14pt; letter-spacing: 0.02em; }
h2 { font-size: 13.5pt; margin: 18pt 0 6pt; }
h3 { font-size: 12pt; margin: 14pt 0 4pt; }
h4 { font-size: 11.5pt; margin: 10pt 0 2pt; }
p { margin: 0 0 6pt; }
ul, ol { margin: 0 0 6pt; padding-left: 1.6em; }
li { margin: 1pt 0; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 10.5pt; line-height: 1.5; }
th, td { border: 0.6pt solid #000; padding: 4pt 6pt; vertical-align: top; text-align: left; }
th { background: #eee; text-align: center; }
tr { break-inside: avoid; }
h1, h2, h3, h4 { break-after: avoid; }
blockquote { margin: 0 0 8pt; padding: 4pt 10pt; border-left: 2pt solid #999; color: #444; font-size: 10pt; }
code { font-family: inherit; background: #f1f1f1; padding: 0 2pt; }
hr { border: 0; border-top: 0.6pt solid #000; margin: 12pt 0; }
.draft { position: fixed; top: 38%; left: 0; right: 0; text-align: center; font-size: 96pt; color: rgba(200,0,0,0.10);
         transform: rotate(-24deg); font-family: sans-serif; font-weight: 700; z-index: -1; }
.hole { background: #ffe8a3; }
"""


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def find_browser():
    env = os.environ.get("BARUCH_BROWSER")
    if env and Path(env).exists():
        return env
    cands = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in cands:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


def holes(text):
    found = []
    for pat in HOLES:
        found += re.findall(pat, text)
    return found


def strip_for_final(text):
    lines = text.splitlines()
    # 1) 제목 앞뒤의 안내 인용 블록 제거 (문서 첫 가로줄·둘째 제목 전까지의 '>' 줄)
    out, seen_body = [], False
    for ln in lines:
        if not seen_body and ln.lstrip().startswith(">"):
            continue
        if ln.strip() and not ln.startswith("#") and not ln.lstrip().startswith(">"):
            seen_body = True
        out.append(ln)
    text = "\n".join(out)
    # 2) 끝의 안내 제거
    if CUT in text:
        text = text.split(CUT)[0]
    else:
        parts = re.split(r"\n-{3,}\s*\n", text)
        if len(parts) > 1:
            tail = parts[-1].strip()
            # 마지막 가로줄 뒤가 '쓰는 사람 안내'(글머리표 목록이나 굵은 안내 제목)일 때만 뺀다
            if tail and all(l.lstrip().startswith(("-", "**쓰는", "*")) or not l.strip() for l in tail.splitlines()):
                text = "\n---\n".join(parts[:-1])
    # 3) 표시 제거
    text = re.sub(r"\s*【[^】]*】", "", text)
    return text.rstrip() + "\n"


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", s)
    for pat in HOLES:
        s = re.sub(pat, lambda m: f'<span class="hole">{m.group(0)}</span>', s)
    return s


def cells(row):
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", row)]


def md_to_html(text):
    L = text.splitlines()
    out, i, para = [], 0, []

    def flush():
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para.clear()

    while i < len(L):
        ln = L[i]
        st = ln.strip()
        if not st:
            flush(); i += 1; continue
        if st.startswith("<!--"):
            flush()
            while i < len(L) and "-->" not in L[i]:
                i += 1
            i += 1; continue
        if st.startswith("```"):
            flush(); i += 1; buf = []
            while i < len(L) and not L[i].strip().startswith("```"):
                buf.append(html.escape(L[i])); i += 1
            i += 1
            out.append("<pre>" + "\n".join(buf) + "</pre>"); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", st)
        if m:
            flush(); n = min(len(m.group(1)), 4)
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); i += 1; continue
        if re.match(r"^-{3,}$", st) or re.match(r"^\*{3,}$", st):
            flush(); out.append("<hr>"); i += 1; continue
        if st.startswith("|") and i + 1 < len(L) and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", L[i + 1]) and "-" in L[i + 1]:
            flush()
            head = cells(st); i += 2; rows = []
            while i < len(L) and L[i].strip().startswith("|"):
                rows.append(cells(L[i])); i += 1
            t = ["<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
            for r in rows:
                r = (r + [""] * len(head))[:max(len(head), len(r))]
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t)); continue
        if st.startswith(">"):
            flush(); buf = []
            while i < len(L) and L[i].strip().startswith(">"):
                buf.append(inline(L[i].strip()[1:].strip())); i += 1
            out.append("<blockquote>" + "<br>".join(buf) + "</blockquote>"); continue
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", ln)
        if m:
            flush()
            stack = []  # (indent, tag)
            html_parts = []
            while i < len(L):
                mm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", L[i])
                if not mm:
                    if L[i].strip() and L[i].startswith((" ", "\t")) and stack:
                        html_parts.append("<br>" + inline(L[i].strip())); i += 1; continue
                    break
                ind = len(mm.group(1).replace("\t", "    "))
                tag = "ol" if mm.group(2)[0].isdigit() else "ul"
                while stack and ind < stack[-1][0]:
                    html_parts.append(f"</li></{stack.pop()[1]}>")
                if not stack or ind > stack[-1][0]:
                    html_parts.append(f"<{tag}>"); stack.append((ind, tag))
                else:
                    html_parts.append("</li>")
                html_parts.append("<li>" + inline(mm.group(3))); i += 1
            while stack:
                html_parts.append(f"</li></{stack.pop()[1]}>")
            out.append("".join(html_parts)); continue
        para.append(st); i += 1
    flush()
    return "\n".join(out)


def build(src, final, outdir, name, browser):
    text = Path(src).read_text(encoding="utf-8")
    if final:
        text = strip_for_final(text)
        left = holes(text)
        if left:
            uniq = sorted(set(left))
            print(f"✗ {Path(src).name}: 빈칸·확인 표시가 {len(left)}곳 남아 제출용 PDF를 만들지 않았습니다.", file=sys.stderr)
            for h in uniq[:12]:
                print(f"    {h}", file=sys.stderr)
            if len(uniq) > 12:
                print(f"    … 외 {len(uniq) - 12}가지", file=sys.stderr)
            return False
    body = md_to_html(text)
    mark = "" if final else '<div class="draft">초안</div>'
    title = html.escape(Path(src).stem)
    page = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title}</title><style>{CSS}</style></head><body>{mark}{body}</body></html>'
    outdir = Path(outdir) if outdir else Path(src).parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = name or (Path(src).stem + ("" if final else "-초안"))
    pdf = outdir / f"{stem}.pdf"
    if not browser:
        h = outdir / f"{stem}.html"
        h.write_text(page, encoding="utf-8")
        print(f"△ 크롬·엣지를 찾지 못해 HTML로 저장했습니다: {h}\n  브라우저로 열어 인쇄 → 'PDF로 저장'을 누르십시오 (머리글·바닥글 끄기).")
        return True
    with tempfile.TemporaryDirectory() as td:
        h = Path(td) / "doc.html"
        h.write_text(page, encoding="utf-8")
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
               f"--user-data-dir={td}/profile", f"--print-to-pdf={pdf.resolve()}", h.as_uri()]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not pdf.exists() or pdf.stat().st_size == 0:
        print(f"✗ {Path(src).name}: PDF를 만들지 못했습니다.\n{r.stderr[-400:]}", file=sys.stderr)
        return False
    kind = "제출용" if final else "초안"
    print(f"✓ {kind} PDF: {pdf}  ({pdf.stat().st_size // 1024} KB)")
    return True


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return
    final = check = False
    outdir = name = None
    files = []
    i = 0
    while i < len(a):
        if a[i] == "--final":
            final = True
        elif a[i] == "--check":
            check = True
        elif a[i] == "-o":
            i += 1; outdir = a[i]
        elif a[i] == "-n":
            i += 1; name = a[i]
        else:
            files.append(a[i])
        i += 1
    if not files:
        die("바꿀 파일을 적으십시오.")
    if name and len(files) > 1:
        die("-n 은 파일이 하나일 때만 씁니다.")
    for f in files:
        if not Path(f).is_file():
            die(f"파일이 없습니다: {f}")
    if check:
        total = 0
        for f in files:
            left = holes(strip_for_final(Path(f).read_text(encoding="utf-8")))
            total += len(left)
            print(f"{len(left):4d}곳  {Path(f).name}")
        print(f"합계 {total}곳" + (" — 제출용 PDF를 만들 수 있습니다." if total == 0 else " — 채운 뒤에 제출용 PDF를 만들 수 있습니다."))
        sys.exit(0 if total == 0 else 2)
    browser = find_browser()
    ok = all([build(f, final, outdir, name, browser) for f in files])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
