"""MCP 서버가 읽을 content.json을 만든다. 레포의 스킬·카드·틀을 그대로 옮긴다.
실행: python3 mcp/build_content.py"""
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def strip_front(s):
    return re.sub(r"\A---\n.*?\n---\n", "", s, flags=re.S).strip()
areas = []
for skill, kind in (("admin-affairs", "관청에 내는 일"), ("judicial-affairs", "법원·등기소에 내는 일")):
    for f in sorted((ROOT / "skills" / skill / "references").glob("*.md")):
        s = f.read_text(encoding="utf-8")
        title = re.search(r"^# (.+)$", s, re.M).group(1).strip()
        parts = re.split(r"^## ", s, flags=re.M)
        head = parts[0].strip()
        intro, cards = [], []
        for p in parts[1:]:
            name, _, body = p.partition("\n")
            name = name.strip()
            if name.startswith(("이 영역에서 먼저 볼 것", "업무 목록")):
                intro.append("## " + name + "\n" + body.strip())
            else:
                cards.append({"name": re.sub(r"^\d+\.\s*", "", name), "text": "## " + name + "\n" + body.strip()})
        areas.append({"id": f.stem, "kind": kind, "title": title, "head": head, "intro": "\n\n".join(intro), "cards": cards})
guides = {}
def g(key, title, path):
    guides[key] = {"title": title, "text": strip_front((ROOT / path).read_text(encoding="utf-8"))}
g("work-engine", "어떤 업무든 따르는 공통 절차", "skills/work-engine/SKILL.md")
g("card-format", "업무 카드 형식", "skills/work-engine/references/카드-형식.md")
g("registry-check", "등기 신청 사전 점검 — 등기 전에 받을 서류 찾기, 놓친 등기, 신청서 대조", "skills/registry-check/SKILL.md")
g("case-file", "공문이 오가는 일을 사건으로 관리 — 받은 공문, 기한 장부, 법 위계, 단체의 일", "skills/case-file/SKILL.md")
g("precheck", "보완 요구를 미리 막기 — 담당자가 물을 질문과 흔한 보완 사유", "skills/nonprofit-incorporation/references/보완-예방.md")
g("sinmungo", "국민신문고로 질의하고 신청하기", "skills/nonprofit-incorporation/references/국민신문고.md")
g("admin-affairs", "관청에 내는 일 — 영역과 고르는 법", "skills/admin-affairs/SKILL.md")
g("judicial-affairs", "법원·등기소에 내는 일 — 영역과 고르는 법", "skills/judicial-affairs/SKILL.md")
g("nonprofit", "비영리 사단법인 설립과 기부금영수증 — 전체 순서", "skills/nonprofit-incorporation/SKILL.md")
guides["office"] = {"title": "직접 고칠 워드 파일로 주기 — 이음오피스가 함께 연결되어 있을 때",
    "text": "대화창에서는 `ieumoffice …` 명령어 대신 **이음오피스 연결 도구**(`create_docx`, `docs_read`, `convert`, `hwp_read`)를 쓴다. 그 도구가 대화에 없으면 이 방법을 쓰지 않는다. 폴더 이름(`업무/…`, `고치기/`)은 대화창에서는 해당이 없고, 원본은 이 대화에서 쓴 초안이다.\n\n---\n\n"
    + strip_front((ROOT / "skills/office-doc/SKILL.md").read_text(encoding="utf-8"))}
CHAT_BUILDING = ("대화창에서는 `arch.py` 대신 **`building_lookup` 도구**를 쓴다. what에 profile · history · floors · temp 가운데 하나를 넣는다. "
                 "동 단위 통계 같은 다른 조회와 원본 행(`raw`)은 대화창에서 되지 않는다. 아래에서 `arch.py …`라고 적힌 곳은 그 도구로 읽는다.\n\n---\n\n")
CHAT_DRAWING = ("대화창에서는 `draw.py` 대신 **`drawing_example`과 `drawing_make` 도구**를 쓴다. 보기 내용을 받아 신청인의 값으로 바꾼 뒤 `drawing_make`의 spec으로 넘기면 SVG가 온다. "
                "받은 SVG는 고치지 말고 그대로 파일로 만들어 보여 준다. PDF와 PNG는 만들어지지 않으니 신청인이 SVG를 브라우저로 열어 A4 가로, 여백 없음으로 인쇄해 PDF로 저장하게 한다. "
                "경사는 `slope_reference` 도구가 숫자만 돌려준다(그림 없음). "
                "**필지 경계 받기(`parcel.py`), 대장 면적 받기, 바탕 지도는 대화창에서 되지 않는다.** 본인 브이월드 인증키가 필요해서 Claude Code 플러그인에서만 쓴다. "
                "대화창에서는 대지경계와 대지면적을 신청인이 뗀 지적도·토지대장에서 읽어 직접 적고, 기존 건물의 `대장면적`은 `building_lookup`이나 건축물대장 등본에서 읽어 적는다.\n\n---\n\n")
guides["building"] = {"title": "건축물대장 조회 — 무엇을 볼 수 있고 무엇을 볼 수 없는지",
                      "text": CHAT_BUILDING + strip_front((ROOT / "skills/building-lookup/SKILL.md").read_text(encoding="utf-8"))}
guides["drawing"] = {"title": "배치도·평면도 그리기 — 그리기 전에 받을 것, 적는 칸",
                     "text": CHAT_DRAWING + strip_front((ROOT / "skills/site-drawing/SKILL.md").read_text(encoding="utf-8"))}
for f in sorted((ROOT / "skills/nonprofit-incorporation/references").glob("*.md")):
    if f.stem in ("보완-예방", "국민신문고"):
        continue
    g("nonprofit/" + f.stem, "비영리 사단법인 — " + f.stem.replace("-", " "), str(f.relative_to(ROOT)))
g("forms", "관청 서식 목록 — 업무별 서식 번호와 원본을 받는 누리집 주소", "skills/office-doc/references/서식-목록.md")
cc = strip_front((ROOT / "skills/cross-check/SKILL.md").read_text(encoding="utf-8"))
sh = strip_front((ROOT / "agents/shaphan.md").read_text(encoding="utf-8"))
na = strip_front((ROOT / "agents/nathan.md").read_text(encoding="utf-8"))
guides["cross-check"] = {"title": "내기 전 검토 — 대조하는 눈(사반)과 받는 쪽의 눈(나단)",
    "text": "대화창에는 따로 검토해 줄 에이전트가 없다. 그래서 서류를 다 쓴 뒤 **쓴 사람의 자리에서 내려와** 아래 두 역할을 차례로 직접 한다. 한 번은 대조만, 한 번은 받는 쪽 자리에서만 읽는다. 검토 결과는 표로 신청인에게 보여 주고, 독립된 검토가 아니라 스스로 한 검토였다고 밝힌다.\n\n---\n\n" + sh + "\n\n---\n\n" + na + "\n\n---\n\n" + cc}
templates = {}
for f in sorted((ROOT / "skills/nonprofit-incorporation/templates").glob("*.md")):
    templates[f.stem] = f.read_text(encoding="utf-8").strip()
rules = (ROOT / "mcp/chat-rules.md").read_text(encoding="utf-8").strip()
ver = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"]
import sys
sys.path.insert(0, str(ROOT / "skills/site-drawing/scripts"))
from draw import EXAMPLES
out = {"version": ver, "rules": rules, "areas": areas, "guides": guides, "templates": templates, "drawingExamples": EXAMPLES}
(ROOT / "mcp/content.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print("영역", len(areas), "카드", sum(len(a["cards"]) for a in areas), "안내", len(guides), "틀", len(templates), (ROOT / "mcp/content.json").stat().st_size // 1024, "KB")
