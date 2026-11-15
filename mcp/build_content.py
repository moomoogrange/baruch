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
for f in sorted((ROOT / "skills/nonprofit-incorporation/references").glob("*.md")):
    if f.stem in ("보완-예방", "국민신문고"):
        continue
    g("nonprofit/" + f.stem, "비영리 사단법인 — " + f.stem.replace("-", " "), str(f.relative_to(ROOT)))
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
out = {"version": ver, "rules": rules, "areas": areas, "guides": guides, "templates": templates}
(ROOT / "mcp/content.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print("영역", len(areas), "카드", sum(len(a["cards"]) for a in areas), "안내", len(guides), "틀", len(templates), (ROOT / "mcp/content.json").stat().st_size // 1024, "KB")
