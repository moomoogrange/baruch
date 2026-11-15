"""도면 그리기 함수 (Vercel 파이썬) — 대화창 연결 서버(mcp.js)가 부른다.

플러그인의 site-drawing 스크립트를 그대로 쓴다. 배포할 때 deploy.sh가 스크립트를 lib/ 에 복사한다.
파일을 쓰지 않고, 받은 값은 저장하지 않는다. 브이월드 인증키가 필요한 일(필지 경계, 바탕 지도)은 하지 않는다.
"""
import json
import sys
import urllib.error
import zlib
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import draw  # noqa: E402
import sheet  # noqa: E402
import slope  # noqa: E402

MAX_BODY = 300_000
MAX_ITEMS = 200
KEY_ONLY = ("바탕", "원점")                       # 인증키가 있어야 쓰는 칸 — 대화창에서는 뺀다


def make_drawing(spec):
    """도면 내용을 점검하고 SVG를 만든다."""
    if not isinstance(spec, dict):
        return {"ok": False, "errors": ["도면 내용은 { } 로 된 값이어야 합니다."]}
    if sum(len(spec.get(k) or []) for k in ("건물", "표시", "치수", "대지경계") if isinstance(spec.get(k), list)) > MAX_ITEMS:
        return {"ok": False, "errors": [f"건물·표시·치수·경계점이 모두 {MAX_ITEMS}개를 넘습니다. 나눠 그리십시오."]}
    dropped = [k for k in KEY_ONLY if k in spec]
    trimmed = {k: v for k, v in spec.items() if k not in KEY_ONLY}
    try:
        ready, problems = draw.prepare(trimmed)
        if problems:
            return {"ok": False, "errors": problems}
        notes = draw.warnings(ready)
        svg, scale = sheet.render(ready, draw.corners, draw.area)
    except (AttributeError, KeyError, TypeError, ValueError, IndexError) as e:
        return {"ok": False, "errors": [f"도면 내용의 꼴이 맞지 않습니다 ({type(e).__name__}: {e}). 보기 파일의 꼴을 따르십시오."]}
    if dropped:
        notes = notes + ["바탕 지도와 필지 경계 받기는 대화창에서 되지 않아 뺐습니다. Claude Code 플러그인에서 본인 브이월드 인증키로 씁니다."]
    return {"ok": True, "kind": ready["종류"], "scale": scale, "warnings": notes, "svg": svg}


def slope_stats(lat, lon, size):
    """가운데 좌표 둘레의 경사 통계. 그림은 만들지 않는다."""
    try:
        lat, lon, size = float(lat), float(lon), float(size or 300)
    except (TypeError, ValueError):
        return {"ok": False, "errors": ["위도, 경도, 범위는 숫자여야 합니다."]}
    if not (33 <= lat <= 39.5 and 124 <= lon <= 132):
        return {"ok": False, "errors": ["위도와 경도가 우리나라 범위 밖입니다. 위도(33~39.5)와 경도(124~132)를 확인하십시오."]}
    if not 200 <= size <= 3000:
        return {"ok": False, "errors": ["범위는 200에서 3000(미터) 사이입니다. 표고 격자가 약 30m라 더 좁으면 뜻이 없습니다."]}
    try:
        grid, slopes = slope.survey(lat, lon, size)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, zlib.error) as e:
        return {"ok": False, "errors": [f"표고 자료를 받지 못했습니다 ({e}). 받지 못한 채로 경사를 짐작해 말하지 않습니다."]}
    stats = slope.summarize(grid, slopes)
    bands, low = [], 0
    for (top, _), share in zip(slope.CLASSES, stats["비율"]):
        bands.append({"구간": f"{low}° 이상 {top}° 미만" if top < 90 else f"{low}° 이상", "면적비율": round(share, 1)})
        low = top
    return {"ok": True, "위도": lat, "경도": lon, "범위": size, "평균경사": round(stats["평균"], 1),
            "평균경사퍼센트": round(stats["평균퍼센트"]), "가장급한칸": round(stats["최대"], 1),
            "25도이상면적비율": round(stats["기준이상"], 1), "최저표고": round(stats["최저표고"]),
            "최고표고": round(stats["최고표고"]), "구간": bands}


def answer(body):
    action = body.get("action") if isinstance(body, dict) else None
    if action == "draw":
        return make_drawing(body.get("spec"))
    if action == "slope":
        return slope_stats(body.get("lat"), body.get("lon"), body.get("size"))
    return {"ok": False, "errors": ["action은 draw 또는 slope 입니다."]}


class handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        if size <= 0 or size > MAX_BODY:
            self.reply(413, {"ok": False, "errors": ["요청이 비었거나 너무 큽니다."]})
            return
        try:
            body = json.loads(self.rfile.read(size).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.reply(400, {"ok": False, "errors": ["요청을 읽지 못했습니다."]})
            return
        self.reply(200, answer(body))

    def do_GET(self):
        self.reply(200, {"name": "baruch-drawing", "actions": ["draw", "slope"]})

    def log_message(self, *args):
        return
