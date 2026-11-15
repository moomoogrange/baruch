#!/bin/sh
# 소개 쪽과 MCP 서버를 한 주소로 배포한다. 레포 밖 임시 폴더에 모아서 올린다.
# 쓰는 법: sh mcp/deploy.sh   (Vercel CLI 로그인 필요)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${TMPDIR:-/tmp}/baruch-deploy"
python3 "$ROOT/docs/tiles_baruch.py" >/dev/null
python3 "$ROOT/docs/build.py" >/dev/null
python3 "$ROOT/mcp/build_content.py"
rm -rf "$OUT"/.vercel "$OUT"/index.html "$OUT"/preview-navy.html "$OUT"/img "$OUT"/tiles "$OUT"/api "$OUT"/content.json "$OUT"/vercel.json
mkdir -p "$OUT/api"
cp -R "$ROOT/docs/index.html" "$ROOT/docs/preview-navy.html" "$ROOT/docs/img" "$ROOT/docs/tiles" "$OUT/"
cp "$ROOT/mcp/api/mcp.js" "$OUT/api/mcp.js"
cp "$ROOT/mcp/content.json" "$ROOT/mcp/vercel.json" "$OUT/"
cd "$OUT"
# 임시 폴더 이름으로 새 프로젝트가 생기지 않게, 원래 프로젝트에 먼저 연결한다
vercel link --yes --project "${VERCEL_PROJECT:-baruch}" ${VERCEL_SCOPE:+--scope "$VERCEL_SCOPE"} >/dev/null
vercel deploy --prod --yes ${VERCEL_SCOPE:+--scope "$VERCEL_SCOPE"}
