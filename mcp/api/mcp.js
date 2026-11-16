// 바룩 MCP 서버 — Claude·ChatGPT 등에서 주소 하나로 붙여 쓰는 연결 서버.
// Streamable HTTP, 상태 없음(요청마다 독립). 의존 패키지 없음.
// 내용은 content.json(레포의 스킬·카드·틀)에서 읽고, 법령은 korean-law-mcp, 건축물대장은 archhub-mcp 공개 서버로 넘긴다.
// 도면은 같은 배포의 파이썬 함수(api/drawing.py)가 그린다.
const C = require('../content.json');
const LAW = process.env.BARUCH_LAW_SERVER || 'https://mcp.gomdori.app/law';
const ARCH = process.env.BARUCH_ARCH_SERVER || 'https://mcp.gomdori.app/archhub';
const SITE = 'https://baruch-ebon.vercel.app';
const PROTOCOLS = ['2025-06-18', '2025-03-26', '2024-11-05'];

const nfc = (s) => String(s || '').normalize('NFC');
const squash = (s) => nfc(s).replace(/[\s·ㆍ․‧,()「」\-–—/]/g, '').toLowerCase();

// ── 내용 찾기 ─────────────────────────────────────────────
function taskList(areaId) {
  const lines = [];
  for (const kind of ['관청에 내는 일', '법원·등기소에 내는 일']) {
    const as = C.areas.filter((a) => a.kind === kind && (!areaId || squash(a.id) === squash(areaId) || squash(a.title).includes(squash(areaId))));
    if (!as.length) continue;
    lines.push(`## ${kind}`);
    for (const a of as) {
      lines.push(`\n### ${a.title} (area: ${a.id})`);
      for (const c of a.cards) lines.push(`- ${c.name}`);
    }
  }
  return lines.join('\n');
}
function findCards(task, areaId) {
  const key = squash(task);
  const words = nfc(task).split(/\s+/).map(squash).filter((w) => w.length > 1);
  const hits = [];
  for (const a of C.areas) {
    if (areaId && squash(a.id) !== squash(areaId)) continue;
    for (const c of a.cards) {
      const n = squash(c.name);
      let score = 0;
      if (n === key) score = 100;
      else if (n.startsWith(key)) score = 80;
      else if (n.includes(key) || key.includes(n)) score = 60;
      else score = words.filter((w) => n.includes(w)).length * 12 + words.filter((w) => squash(c.text).includes(w)).length * 2;
      if (score > 0) hits.push({ a, c, score });
    }
  }
  return hits.sort((x, y) => y.score - x.score || x.c.name.length - y.c.name.length);
}
function searchAll(query) {
  const words = nfc(query).split(/\s+/).map(squash).filter((w) => w.length > 1);
  const out = [];
  const add = (id, title, text) => {
    const t = squash(title), b = squash(text);
    const score = words.reduce((s, w) => s + (t.includes(w) ? 10 : 0) + (b.includes(w) ? 1 : 0), 0);
    if (score > 0) out.push({ id, title, score });
  };
  for (const a of C.areas) for (const c of a.cards) add(`card:${a.id}:${c.name}`, `${a.title} — ${c.name}`, c.text);
  for (const [k, g] of Object.entries(C.guides)) add(`guide:${k}`, g.title, g.text);
  for (const [k, t] of Object.entries(C.templates)) add(`template:${k}`, `틀 — ${k}`, t);
  return out.sort((x, y) => y.score - x.score).slice(0, 10);
}
function fetchDoc(id) {
  const [type, ...rest] = String(id).split(':');
  if (type === 'card') {
    const a = C.areas.find((x) => x.id === nfc(rest[0]));
    const c = a && a.cards.find((x) => x.name === nfc(rest.slice(1).join(':')));
    if (c) return { title: `${a.title} — ${c.name}`, text: c.text };
  } else if (type === 'guide' && C.guides[nfc(rest.join(':'))]) {
    const g = C.guides[nfc(rest.join(':'))];
    return { title: g.title, text: g.text };
  } else if (type === 'template' && C.templates[nfc(rest.join(':'))]) {
    return { title: `틀 — ${rest.join(':')}`, text: C.templates[nfc(rest.join(':'))] };
  }
  return null;
}

// ── 법령 조회 (공개 서버로 넘김) ───────────────────────────
async function mcpPost(url, body, sid) {
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };
  if (sid) headers['mcp-session-id'] = sid;
  const r = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
  const next = r.headers.get('mcp-session-id') || sid;
  const txt = await r.text();
  let out = null;
  for (const line of txt.split('\n')) if (line.startsWith('data: ')) out = JSON.parse(line.slice(6));
  if (!out && txt.trim().startsWith('{')) out = JSON.parse(txt);
  return { out, sid: next };
}
const lawPost = (body, sid) => mcpPost(LAW, body, sid);
async function lawSession() {
  const { sid } = await lawPost({ jsonrpc: '2.0', id: 0, method: 'initialize', params: { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'baruch-mcp', version: C.version } } });
  try { await lawPost({ jsonrpc: '2.0', method: 'notifications/initialized' }, sid); } catch (e) { /* 무시 */ }
  return sid;
}
async function lawCall(tool, args, sid) {
  sid = sid || (await lawSession());
  const { out } = await lawPost({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: tool, arguments: args } }, sid);
  const r = (out && (out.result || out)) || {};
  const texts = (r.content || []).filter((c) => c.type === 'text').map((c) => c.text);
  return texts.length ? texts.join('\n') : JSON.stringify(r).slice(0, 4000);
}
async function lawFind(name, sid) {
  const txt = await lawCall('search_law', { query: name, display: 10 }, sid);
  const key = squash(name);
  let best = null;
  const re = /^\s*\d+\.\s*(.+?)\s*\[(.+?)\]\s*\n(?:.*\n){0,2}?.*MST:\s*(\d+)/gm;
  let m;
  while ((m = re.exec(txt))) {
    if (squash(m[1]) === key) return { mst: m[3], title: m[1] };
    best = best || { mst: m[3], title: m[1] };
  }
  if (!best) throw new Error(`'${name}'을 현행 법령에서 찾지 못했습니다. law_search로 이름을 먼저 확인하십시오.\n${txt.slice(0, 500)}`);
  return best;
}
const jo = (x) => (String(x).startsWith('제') ? String(x) : `제${x}조`);

// ── 건축물 조회 (공개 서버로 넘김) ─────────────────────────
const ARCH_TOOLS = { profile: 'building_profile', history: 'parcel_history', floors: 'building_floors', temp: 'temp_buildings' };
async function archCall(tool, args, sid) {
  if (!sid) {
    sid = (await mcpPost(ARCH, { jsonrpc: '2.0', id: 0, method: 'initialize', params: { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'baruch-mcp', version: C.version } } })).sid;
    try { await mcpPost(ARCH, { jsonrpc: '2.0', method: 'notifications/initialized' }, sid); } catch (e) { /* 무시 */ }
  }
  const { out } = await mcpPost(ARCH, { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: tool, arguments: args } }, sid);
  const r = (out && (out.result || out)) || {};
  const text = (r.content || []).filter((c) => c.type === 'text').map((c) => c.text).join('\n') || JSON.stringify(r).slice(0, 4000);
  return { text, failed: Boolean(r.isError || (out && out.error)), sid };
}
function splitAddress(address) {
  const region = [];
  let bun = '', ji = '';
  for (const w of nfc(address).split(/\s+/).filter(Boolean)) {
    const m = /^(\d{1,4})(?:-(\d{1,4}))?(?:번지)?$/.exec(w);
    if (m && !bun) { bun = m[1]; ji = m[2] || ''; } else region.push(w);
  }
  return { region, bun, ji };
}
async function buildingLookup(address, what) {
  const tool = ARCH_TOOLS[what || 'profile'];
  if (!tool) throw new Error('what은 profile(종합카드) · history(필지 연혁) · floors(층별) · temp(가설건축물) 가운데 하나입니다.');
  const { region, bun, ji } = splitAddress(address);
  if (!region.length) throw new Error('동 이름이 없습니다. 예: 광진구 자양동 2-2');
  if (!bun && what !== 'temp') throw new Error('번지가 필요합니다. 예: 광진구 자양동 2-2. 도로명주소로는 찾지 못하니 지번을 물으십시오.');
  const found = await archCall('find_region', { keyword: region.join(' '), limit: 30 });
  if (found.failed || found.text.includes('[NOT_FOUND]')) throw new Error(`지역을 찾지 못했습니다. 행정동(자양1동)이 아니라 법정동(자양동) 이름으로 다시 찾으십시오.\n${found.text.slice(0, 400)}`);
  const rows = [];
  for (const line of found.text.split('\n')) {
    const m = /^\s*(.+?)\s+(\d{5})\s+(\d{5})(?:\s+\S.*)?$/.exec(line);
    if (m && m[3] !== '00000') rows.push({ name: m[1].trim().replace(/\s+/g, ' '), sigungu: m[2], bdong: m[3] });
  }
  if (!rows.length) throw new Error('동 단위 코드를 찾지 못했습니다. 읍·면·동 이름까지 적으십시오.');
  if (rows.length > 1) throw new Error(`같은 이름의 지역이 ${rows.length}곳입니다. 시·군·구(리 단위면 읍·면과 리)까지 적어 하나로 좁히십시오.\n${rows.map((r) => `- ${r.name}`).join('\n')}`);
  const args = { sigungu_code: rows[0].sigungu, bdong_code: rows[0].bdong };
  if (bun) args.bun = bun;
  if (ji) args.ji = ji;
  const r = await archCall(tool, args, found.sid);
  if (r.failed) throw new Error(`조회하지 못했습니다. 이 결과로 건물 사실을 적지 않습니다.\n${r.text.slice(0, 600)}`);
  const today = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10); // 한국 날짜
  return `[건축HUB 조회 · ${rows[0].name} ${bun}${ji ? `-${ji}` : ''} · 조회일 ${today}]\n${r.text}\n\n이 결과는 대조용이다. 관청에 낼 때는 신청인이 정부24나 세움터에서 뗀 건축물대장 등본으로 다시 맞춘다. 위반건축물 표시, 소유자, 토지 정보는 여기에 나오지 않는다. 조회되지 않았다고 건물이 없다는 뜻은 아니다. 결과에 섞인 남의 이름은 서류에 옮기지 않는다.`;
}

// ── 도면 (같은 배포의 파이썬 함수) ─────────────────────────
async function drawingCall(base, body) {
  const r = await fetch(`${base}/api/drawing`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const txt = await r.text();
  try { return JSON.parse(txt); } catch (e) { throw new Error(`도면 함수가 답하지 않았습니다 (${r.status}).`); }
}
const bullets = (items) => (items || []).map((x) => `- ${x}`).join('\n');

// ── 도구 ──────────────────────────────────────────────────
const S = (props, required) => ({ type: 'object', properties: props, required: required || [], additionalProperties: false });
const RO = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false };
const TOOLS = [
  { name: 'baruch_start', title: '바룩 시작',
    description: '행정사·법무사에게 맡기던 서류 일(등기, 인허가·변경신고, 처분 불복, 지급명령·소장, 가압류, 상속포기, 개인회생, 비영리법인 설립 등 관청·법원·등기소에 내는 신청)을 사용자가 직접 하려 할 때 **맨 먼저** 부른다. 바룩으로 일하는 규칙, 공통 절차, 다룰 수 있는 업무 목록을 돌려준다. 받은 규칙을 대화가 끝날 때까지 따른다. situation에는 일의 종류만 한 줄로 적고 이름·주소·주민등록번호 같은 개인정보는 넣지 않는다.',
    inputSchema: S({ situation: { type: 'string', description: '무슨 일인지 한 줄 (예: 대표이사 주소 변경등기, 식당 인수, 과태료 통지서, 상속포기). 개인정보 금지.' } }), annotations: RO },
  { name: 'baruch_tasks', title: '업무 목록',
    description: '바룩이 카드로 가지고 있는 업무 목록. area를 주면 그 영역만 본다. 사용자의 사정에 걸리는 업무를 빠짐없이 찾을 때 쓴다.',
    inputSchema: S({ area: { type: 'string', description: '영역 id 또는 이름 (예: 법인-등기, 영업-인허가). 비우면 전체.' } }), annotations: RO },
  { name: 'baruch_card', title: '업무 카드',
    description: '업무 하나의 카드: 무엇을, 누가·언제(기한), 어디에, 근거 조문, 먼저 할 것, 내는 서류, 돈, 걸리는 날, 자주 돌아오는 까닭, 낸 뒤 할 일, 전문가가 필요한 선. 카드는 출발점이므로 적힌 조문과 기한은 law_article로 다시 확인한다. with_intro를 true로 하면 그 영역 전체에 걸치는 "먼저 볼 것"도 함께 준다(영역을 처음 다룰 때 켠다).',
    inputSchema: S({ task: { type: 'string', description: '업무 이름 (baruch_tasks 목록의 이름 또는 그 일부)' }, area: { type: 'string', description: '영역 id (같은 이름이 여러 영역에 있을 때)' }, with_intro: { type: 'boolean', description: '영역의 "먼저 볼 것"을 함께 받을지' } }, ['task']), annotations: RO },
  { name: 'baruch_guide', title: '절차 안내',
    description: '절차 문서를 읽는다. name: work-engine(카드가 없는 일을 근거법부터 처리하는 공통 절차) · registry-check(등기 전 받을 서류, 놓친 등기, 신청서 대조 — 등기는 반드시) · case-file(관청과 공문이 오가는 일, 불복 기한 장부, 단체의 일) · precheck(담당자가 물을 질문과 보완 예방) · cross-check(내기 전 두 번의 검토) · sinmungo(국민신문고) · nonprofit(비영리 사단법인 설립 전체 순서) · nonprofit/유형-고르기 · nonprofit/주무관청-찾기 · nonprofit/설립허가-서류 · nonprofit/설립등기 · nonprofit/세무와-기부금영수증 · nonprofit/설립-뒤-할-일 · nonprofit/생활법령-요점 · admin-affairs · judicial-affairs · card-format · building(건축물대장 조회 — 무엇을 볼 수 있고 무엇을 볼 수 없는지) · drawing(배치도·평면도 그리기 — 그리기 전에 받을 것, 적는 칸) · forms(관청 서식 목록 — 업무별 서식 번호와 원본 한글·PDF를 받는 누리집 주소) · iros-forms(등기소에 내는 등기신청양식 목록 — 인터넷등기소 자료센터) · office(이음오피스 도구가 함께 연결되어 있을 때 초안을 워드 파일로 주고, 신청인이 타이핑해 고친 파일을 다시 읽는 법)',
    inputSchema: S({ name: { type: 'string', description: '문서 이름' } }, ['name']), annotations: RO },
  { name: 'baruch_template', title: '서류 틀',
    description: '서류 틀을 받는다. name을 비우면 목록. 지금 있는 틀은 비영리 사단법인 설립용(정관, 창립총회 회의록, 설립취지서, 사업계획서·예산서, 재산목록, 발기인·임원 서류, 회원 명부, 보충 설명서, 설립등기 준비표, 기한 장부)이다. {{…}}는 채울 자리이고 모르는 것은 [확인 필요: …]로 바꿔 적는다.',
    inputSchema: S({ name: { type: 'string', description: '틀 이름. 비우면 목록.' } }), annotations: RO },
  { name: 'law_search', title: '법령 찾기',
    description: '현행 법령·조례·행정규칙을 이름으로 찾는다(법제처 Open API). 법령의 정확한 이름과 시행일을 확인할 때 쓴다. query에는 법령 이름이나 낱말만 넣는다.',
    inputSchema: S({ query: { type: 'string' } }, ['query']), annotations: { ...RO, openWorldHint: true } },
  { name: 'law_article', title: '조문 읽기',
    description: '현행 조문 하나를 읽는다. 기한·금액·요건·서류를 말하기 전에 반드시 읽고 법령명·조 번호·시행일을 함께 적는다. date(YYYYMMDD)를 주면 그날 시행 중이던 조문을 읽는다(이미 받은 처분, 오래된 허가·계약).',
    inputSchema: S({ law: { type: 'string', description: '법령 이름 (예: 민법, 법인세법 시행령)' }, article: { type: 'string', description: '조 번호 (예: 제32조, 제18조의3)' }, date: { type: 'string', description: '기준일 YYYYMMDD (선택)' } }, ['law', 'article']), annotations: { ...RO, openWorldHint: true } },
  { name: 'law_articles', title: '조문 여럿 읽기',
    description: '한 법령의 조문 여러 개를 한 번에 읽는다. 같은 법의 조문을 둘 이상 볼 때는 law_article을 되풀이하지 말고 이것을 쓴다.',
    inputSchema: S({ law: { type: 'string' }, articles: { type: 'array', items: { type: 'string' }, description: '조 번호 목록 (예: ["제32조","제49조"])' } }, ['law', 'articles']), annotations: { ...RO, openWorldHint: true } },
  { name: 'law_annex', title: '별표·서식 찾기',
    description: '법령의 별표와 별지 서식을 찾는다. no를 비우면 목록(20건까지), 번호를 주면 그 별표·서식의 내용. 신청서 서식 번호와 첨부서류를 확인할 때 쓴다.',
    inputSchema: S({ law: { type: 'string', description: '법령 이름 (보통 시행규칙)' }, no: { type: 'string', description: '별표·서식 번호 (선택)' } }, ['law']), annotations: { ...RO, openWorldHint: true } },
  { name: 'building_lookup', title: '건축물대장 조회',
    description: '주소(시·군·구 법정동 번지)로 건축물대장과 건축 인허가 기록을 읽는다(국토교통부 건축HUB). 건물이 걸린 신청(건축신고, 용도변경, 가설건축물, 영업신고 전 건물 용도 확인)에서 건물의 용도·구조·면적·사용승인일을 서류에 적기 전에 부른다. what: profile(종합카드 — 용도지역, 주용도, 구조, 면적, 사용승인일, 정화조) · history(허가·착공·사용승인·철거 연혁) · floors(층별 용도와 면적) · temp(가설건축물과 존치기간 만료일). address에는 지번 주소만 넣고 사람 이름·상호는 넣지 않는다. 도로명주소로는 찾지 못한다.',
    inputSchema: S({ address: { type: 'string', description: '시·군·구 법정동 번지 (예: 광진구 자양동 2-2). 개인정보 금지.' }, what: { type: 'string', enum: ['profile', 'history', 'floors', 'temp'], description: '무엇을 볼지. 비우면 profile.' } }, ['address']), annotations: { ...RO, openWorldHint: true } },
  { name: 'drawing_example', title: '도면 보기 파일',
    description: '배치도·평면도를 그릴 때 채워 넣을 보기 내용(JSON)과 적는 법을 받는다. 가설건축물 축조신고처럼 배치도·평면도를 붙이라는 신청에서 drawing_make 앞에 부른다. 적는 칸의 뜻은 baruch_guide의 drawing에 있다.',
    inputSchema: S({ kind: { type: 'string', enum: ['배치도', '평면도'], description: '보기의 종류' } }, ['kind']), annotations: RO },
  { name: 'drawing_make', title: '도면 그리기',
    description: '신청인이 말한 치수로 배치도·평면도·현황도를 A4 가로 SVG로 그린다. spec은 drawing_example이 준 꼴의 내용이다. 길이와 좌표는 미터, x는 오른쪽, y는 위쪽. 방위와 위치근거(자리와 거리를 어디서 얻었는지)가 없으면 그리지 않는다. 자리·거리·방위·경계를 짐작해 채우지 않고 신청인에게 받은 값만 넣는다. 받은 SVG는 고치지 말고 그대로 파일로 만들어 신청인에게 보여 주고 자리가 맞는지 확인받는다.',
    inputSchema: { type: 'object', properties: { spec: { type: 'object', description: '도면 내용 (drawing_example의 꼴)', additionalProperties: true } }, required: ['spec'], additionalProperties: false }, annotations: RO },
  { name: 'slope_reference', title: '경사 참고값',
    description: '위도·경도 둘레 땅의 평균 경사, 경사 구간별 면적 비율, 표고 범위를 공개 표고 자료(격자 약 30m)로 계산한다. 산지전용·개발행위처럼 경사가 걸리는 일을 시작할 때 미리 보는 참고값이다. 평균경사도 조사서를 대신하지 못하고, 건물 한 채 크기의 경사는 알 수 없다. 좌표는 신청인이 지도 앱에서 읽어 준 값을 넣는다.',
    inputSchema: S({ lat: { type: 'number', description: '위도 (33~39.5)' }, lon: { type: 'number', description: '경도 (124~132)' }, size: { type: 'number', description: '한 변의 길이(미터, 200~3000). 비우면 300.' } }, ['lat', 'lon']), annotations: { ...RO, openWorldHint: true } },
  { name: 'search', title: '바룩 문서 검색',
    description: '바룩의 업무 카드·절차 안내·서류 틀을 낱말로 검색한다. 결과의 id를 fetch에 넘겨 본문을 읽는다.',
    inputSchema: S({ query: { type: 'string' } }, ['query']), annotations: RO },
  { name: 'fetch', title: '바룩 문서 읽기',
    description: 'search 결과의 id로 문서 본문을 읽는다.',
    inputSchema: S({ id: { type: 'string' } }, ['id']), annotations: RO },
];

async function callTool(name, a, base) {
  a = a || {};
  switch (name) {
    case 'baruch_start': {
      const hits = a.situation ? findCards(a.situation).slice(0, 6) : [];
      const guess = hits.length ? `\n\n## 이 사정과 가까워 보이는 카드\n${hits.map((h) => `- ${h.c.name} (area: ${h.a.id})`).join('\n')}\n이것은 낱말로 찾은 후보일 뿐이다. 아래 전체 목록에서 걸리는 업무를 직접 다시 고른다.` : '';
      return `${C.rules}${guess}\n\n---\n\n# 업무 목록 (baruch_card로 읽는다)\n\n${taskList()}\n\n---\n\n다음: 걸리는 업무마다 \`baruch_card\`를 부른다. 영역을 처음 다루면 with_intro를 켠다. 등기는 \`baruch_guide\`의 registry-check를, 공문이 오가는 일과 단체의 일은 case-file을 함께 읽는다. 목록에 없는 일은 work-engine을 읽고 law_search로 근거법부터 찾는다.\n\n(바룩 ${C.version} · ${SITE})`;
    }
    case 'baruch_tasks': {
      const t = taskList(a.area);
      return t || `'${a.area}' 영역이 없습니다. 영역: ${C.areas.map((x) => x.id).join(', ')}`;
    }
    case 'baruch_card': {
      const hits = findCards(a.task, a.area);
      if (!hits.length) return `'${a.task}'에 맞는 카드를 찾지 못했습니다. baruch_tasks로 목록을 보거나, 카드가 없는 일이면 baruch_guide의 work-engine 순서로 근거법부터 찾으십시오.`;
      const top = hits[0];
      const others = hits.slice(1, 5).filter((h) => h.score >= top.score * 0.5);
      let out = '';
      if (others.length) out += `> 이 이름에 걸리는 카드가 더 있다. 지금 보여 주는 것은 「${top.c.name}」(area: ${top.a.id})이다. 다른 카드: ${others.map((h) => `「${h.c.name}」(area: ${h.a.id})`).join(', ')}. 사정에 맞는 카드를 area와 함께 다시 불러 읽는다. 여러 카드가 함께 걸리는 일이 흔하다.\n\n`;
      out += `${top.a.head}\n\n`;
      if (a.with_intro) out += `${top.a.intro}\n\n---\n\n`;
      out += top.c.text;
      return out;
    }
    case 'baruch_guide': {
      const k = Object.keys(C.guides).find((x) => squash(x) === squash(a.name)) || Object.keys(C.guides).find((x) => squash(x).includes(squash(a.name)));
      if (!k) return `'${a.name}' 문서가 없습니다. 있는 문서:\n${Object.entries(C.guides).map(([n, g]) => `- ${n} — ${g.title}`).join('\n')}`;
      return `# ${C.guides[k].title}\n\n${C.guides[k].text}`;
    }
    case 'baruch_template': {
      if (!a.name) return `있는 틀:\n${Object.keys(C.templates).map((n) => `- ${n}`).join('\n')}`;
      const k = Object.keys(C.templates).find((x) => squash(x) === squash(a.name)) || Object.keys(C.templates).find((x) => squash(x).includes(squash(a.name)));
      return k ? C.templates[k] : `'${a.name}' 틀이 없습니다. 있는 틀: ${Object.keys(C.templates).join(', ')}`;
    }
    case 'law_search':
      return lawCall('search_law', { query: a.query, display: 10 });
    case 'law_article': {
      const sid = await lawSession();
      const f = await lawFind(a.law, sid);
      const args = { mst: f.mst, jo: jo(a.article) };
      if (a.date) args.efYd = String(a.date);
      return `[현행 조회 · ${f.title}${a.date ? ` · 기준일 ${a.date}` : ''}]\n${await lawCall('get_law_text', args, sid)}`;
    }
    case 'law_articles': {
      const sid = await lawSession();
      const f = await lawFind(a.law, sid);
      return `[현행 조회 · ${f.title} · ${a.articles.length}개 조문]\n${await lawCall('execute_tool', { tool_name: 'get_batch_articles', params: { mst: f.mst, articles: a.articles.map(jo) } }, sid)}`;
    }
    case 'law_annex': {
      const args = { lawName: a.law };
      if (a.no) args.annexNo = String(a.no);
      return lawCall('get_annexes', args);
    }
    case 'building_lookup':
      return buildingLookup(a.address, a.what);
    case 'drawing_example': {
      const ex = C.drawingExamples[nfc(a.kind)];
      if (!ex) throw new Error('kind는 배치도 또는 평면도입니다.');
      return `아래 내용을 신청인의 값으로 바꿔 drawing_make의 spec으로 넘긴다. 길이와 좌표는 모두 미터이고 x는 도면의 오른쪽, y는 위쪽으로 커진다. 칸의 뜻은 baruch_guide의 drawing에 있다. 모르는 값(새 건물이 놓일 자리, 방위, 경계)은 짐작하지 말고 신청인에게 묻는다.\n\n${JSON.stringify(ex, null, 2)}`;
    }
    case 'drawing_make': {
      const r = await drawingCall(base, { action: 'draw', spec: a.spec });
      if (!r.ok) throw new Error(`고쳐야 그릴 수 있습니다.\n${bullets(r.errors)}`);
      const notes = r.warnings.length ? `\n\n살필 것:\n${bullets(r.warnings)}` : '';
      return `${r.kind} · 축척 1/${r.scale} · A4 가로 (297×210mm)${notes}\n\n아래 SVG를 한 글자도 고치지 말고 그대로 파일(.svg)로 만들어 신청인에게 보여 준다. 신청인에게 건물 자리, 방위, 치수가 맞는지 확인받는다. 내려면 SVG를 브라우저로 열어 용지 A4 가로, 여백 없음으로 인쇄해 PDF로 저장한다. 이 도면은 신청인이 그린 도면이고 측량 성과가 아니며, 관청이 다른 꼴(지적도 위 표시 등)을 원할 수 있다고 알린다.\n\n${r.svg}`;
    }
    case 'slope_reference': {
      const r = await drawingCall(base, { action: 'slope', lat: a.lat, lon: a.lon, size: a.size });
      if (!r.ok) throw new Error(bullets(r.errors));
      return `[경사 참고값 · 북위 ${r['위도']} 동경 ${r['경도']} 둘레 ${r['범위']}×${r['범위']}m]\n평균 경사 ${r['평균경사']}° (${r['평균경사퍼센트']}%) · 가장 급한 칸 ${r['가장급한칸']}° · 25° 이상 면적 ${r['25도이상면적비율']}% · 표고 ${r['최저표고']}~${r['최고표고']}m\n${r['구간'].map((b) => `- ${b['구간']}: ${b['면적비율']}%`).join('\n')}\n\n참고값이다. 표고 자료(Mapzen Terrain Tiles, 원자료 SRTM 등)의 격자가 약 30m라 건물 한 채나 작은 필지의 경사는 나타나지 않고, 나무와 건물 높이가 섞여 숲과 시가지는 실제보다 급하게 나올 수 있다. 산지전용 등에 내는 평균경사도 조사서를 대신하지 못한다. 이 숫자를 신청서에 평균경사도로 옮겨 적지 않는다.`;
    }
    case 'search':
      return JSON.stringify({ results: searchAll(a.query).map((r) => ({ id: r.id, title: r.title, url: `${SITE}/#work` })) });
    case 'fetch': {
      const d = fetchDoc(a.id);
      if (!d) throw new Error(`문서를 찾지 못했습니다: ${a.id}`);
      return JSON.stringify({ id: a.id, title: d.title, text: d.text, url: `${SITE}/#work` });
    }
    default:
      throw new Error(`없는 도구입니다: ${name}`);
  }
}

const PROMPTS = [
  { name: 'baruch', title: '바룩으로 서류 일 시작하기', description: '사정을 말하면 걸리는 신청, 기한, 낼 서류를 정리하고 초안을 쓴다.', arguments: [{ name: 'situation', description: '무슨 일인지 (예: 대표이사가 이사를 했어요)', required: false }] },
];
const INSTRUCTIONS = '바룩 — 행정사·법무사에게 맡기던 서류 일을 본인이 직접 하도록 돕는다. 관청·법원·등기소에 내는 신청(등기, 인허가·변경신고, 처분 불복, 지급명령·소장, 가압류·공탁, 상속포기·개명, 개인회생, 법인·단체 설립)이 나오면 먼저 baruch_start를 부르고 받은 규칙을 따른다. 기한·금액·요건은 law_article로 현행 조문을 읽은 뒤에만 말한다. 건물의 용도·면적은 building_lookup으로 대장 기록을 읽은 뒤에 적고, 배치도·평면도는 신청인에게 받은 치수로 drawing_make로 그린다. 도구 인자에는 개인정보를 넣지 않는다. 법률 자문이 아니며 결과를 보장하지 않는다.';

async function handle(msg, base) {
  const { id, method, params } = msg;
  const ok = (result) => ({ jsonrpc: '2.0', id, result });
  const err = (code, message) => ({ jsonrpc: '2.0', id, error: { code, message } });
  if (id === undefined || id === null) return null; // 알림
  try {
    switch (method) {
      case 'initialize': {
        const want = params && params.protocolVersion;
        return ok({ protocolVersion: PROTOCOLS.includes(want) ? want : PROTOCOLS[0], capabilities: { tools: { listChanged: false }, prompts: { listChanged: false } },
          serverInfo: { name: 'baruch', title: '바룩', version: C.version }, instructions: INSTRUCTIONS });
      }
      case 'ping': return ok({});
      case 'tools/list': return ok({ tools: TOOLS });
      case 'tools/call': {
        const name = params && params.name;
        if (!TOOLS.find((t) => t.name === name)) return err(-32602, `없는 도구입니다: ${name}`);
        try {
          const text = await callTool(name, (params && params.arguments) || {}, base);
          return ok({ content: [{ type: 'text', text }], isError: false });
        } catch (e) {
          return ok({ content: [{ type: 'text', text: `오류: ${e.message}` }], isError: true });
        }
      }
      case 'prompts/list': return ok({ prompts: PROMPTS });
      case 'prompts/get': {
        if (!params || params.name !== 'baruch') return err(-32602, '없는 프롬프트입니다');
        const s = (params.arguments && params.arguments.situation) || '';
        return ok({ description: PROMPTS[0].description, messages: [{ role: 'user', content: { type: 'text', text: `바룩으로 서류 일을 도와주세요. 먼저 baruch_start 도구를 불러 규칙을 읽고 그대로 따라 주세요.${s ? `\n\n제 사정: ${s}` : ''}` } }] });
      }
      case 'resources/list': return ok({ resources: [] });
      case 'resources/templates/list': return ok({ resourceTemplates: [] });
      default: return err(-32601, `지원하지 않는 요청입니다: ${method}`);
    }
  } catch (e) {
    return err(-32603, e.message);
  }
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'content-type, accept, authorization, mcp-session-id, mcp-protocol-version, last-event-id');
  res.setHeader('Access-Control-Allow-Methods', 'POST, GET, DELETE, OPTIONS');
  res.setHeader('Access-Control-Expose-Headers', 'mcp-session-id');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method === 'GET') {
    if (String(req.headers.accept || '').includes('text/event-stream')) return res.status(405).json({ jsonrpc: '2.0', id: null, error: { code: -32000, message: '이 서버는 서버가 먼저 보내는 스트림을 쓰지 않습니다.' } });
    return res.status(200).json({ name: 'baruch', version: C.version, transport: 'streamable-http', info: SITE, tools: TOOLS.map((t) => t.name) });
  }
  if (req.method === 'DELETE') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).end();
  let body = req.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) { body = null; } }
  if (!body) return res.status(400).json({ jsonrpc: '2.0', id: null, error: { code: -32700, message: '요청을 읽지 못했습니다.' } });
  const batch = Array.isArray(body);
  const base = process.env.BARUCH_DRAW_BASE || `https://${req.headers.host}`;
  const outs = (await Promise.all((batch ? body : [body]).map((m) => handle(m, base)))).filter(Boolean);
  if (!outs.length) return res.status(202).end();
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  return res.status(200).send(JSON.stringify(batch ? outs : outs[0]));
};
