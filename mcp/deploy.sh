#!/bin/sh
# 소개 쪽과 MCP 서버를 한 주소로 배포한다. 레포 밖 임시 폴더에 모아서 올린다.
# 쓰는 법: sh mcp/deploy.sh   (Vercel CLI 로그인 필요)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${TMPDIR:-/tmp}/baruch-deploy"
python3 "$ROOT/docs/tiles_baruch.py" >/dev/null
python3 "$ROOT/docs/build.py" >/dev/null
python3 "$ROOT/mcp/build_content.py"
rm -rf "$OUT"/.vercel "$OUT"/index.html "$OUT"/img "$OUT"/tiles "$OUT"/api "$OUT"/lib "$OUT"/content.json "$OUT"/vercel.json
mkdir -p "$OUT/api" "$OUT/lib"
cp -R "$ROOT/docs/index.html" "$ROOT/docs/img" "$ROOT/docs/tiles" "$OUT/"
cp "$ROOT/mcp/api/mcp.js" "$ROOT/mcp/api/drawing.py" "$OUT/api/"
# 도면 함수가 쓰는 플러그인 스크립트 (인증키가 필요한 parcel·basemap은 올리지 않는다)
for f in draw sheet slope geo; do cp "$ROOT/skills/site-drawing/scripts/$f.py" "$OUT/lib/"; done
cp "$ROOT/mcp/content.json" "$ROOT/mcp/vercel.json" "$OUT/"
cd "$OUT"
# 임시 폴더 이름으로 새 프로젝트가 생기지 않게, 원래 프로젝트에 먼저 연결한다
vercel link --yes --project "${VERCEL_PROJECT:-baruch}" ${VERCEL_SCOPE:+--scope "$VERCEL_SCOPE"} >/dev/null
vercel deploy --prod --yes ${VERCEL_SCOPE:+--scope "$VERCEL_SCOPE"}
