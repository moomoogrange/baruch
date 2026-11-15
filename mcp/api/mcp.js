// 바룩 MCP 서버 — Claude·ChatGPT 등에서 주소 하나로 붙여 쓰는 연결 서버.
// Streamable HTTP, 상태 없음(요청마다 독립). 의존 패키지 없음.
// 내용은 content.json(레포의 스킬·카드·틀)에서 읽고, 법령은 korean-law-mcp 공개 서버로 넘긴다.
const C = require('../content.json');
const LAW = process.env.BARUCH_LAW_SERVER || 'https://mcp.gomdori.app/law';
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
async function lawPost(body, sid) {
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };
  if (sid) headers['mcp-session-id'] = sid;
  const r = await fetch(LAW, { method: 'POST', headers, body: JSON.stringify(body) });
  const next = r.headers.get('mcp-session-id') || sid;
  const txt = await r.text();
  let out = null;
  for (const line of txt.split('\n')) if (line.startsWith('data: ')) out = JSON.parse(line.slice(6));
  if (!out && txt.trim().startsWith('{')) out = JSON.parse(txt);
  return { out, sid: next };
}
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
    description: '절차 문서를 읽는다. name: work-engine(카드가 없는 일을 근거법부터 처리하는 공통 절차) · registry-check(등기 전 받을 서류, 놓친 등기, 신청서 대조 — 등기는 반드시) · case-file(관청과 공문이 오가는 일, 불복 기한 장부, 단체의 일) · precheck(담당자가 물을 질문과 보완 예방) · cross-check(내기 전 두 번의 검토) · sinmungo(국민신문고) · nonprofit(비영리 사단법인 설립 전체 순서) · nonprofit/유형-고르기 · nonprofit/주무관청-찾기 · nonprofit/설립허가-서류 · nonprofit/설립등기 · nonprofit/세무와-기부금영수증 · nonprofit/설립-뒤-할-일 · nonprofit/생활법령-요점 · admin-affairs · judicial-affairs · card-format',
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
  { name: 'search', title: '바룩 문서 검색',
    description: '바룩의 업무 카드·절차 안내·서류 틀을 낱말로 검색한다. 결과의 id를 fetch에 넘겨 본문을 읽는다.',
    inputSchema: S({ query: { type: 'string' } }, ['query']), annotations: RO },
  { name: 'fetch', title: '바룩 문서 읽기',
    description: 'search 결과의 id로 문서 본문을 읽는다.',
    inputSchema: S({ id: { type: 'string' } }, ['id']), annotations: RO },
];

async function callTool(name, a) {
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
      out += `# ${top.a.title}\n\n${top.a.head}\n\n`;
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
const INSTRUCTIONS = '바룩 — 행정사·법무사에게 맡기던 서류 일을 본인이 직접 하도록 돕는다. 관청·법원·등기소에 내는 신청(등기, 인허가·변경신고, 처분 불복, 지급명령·소장, 가압류·공탁, 상속포기·개명, 개인회생, 법인·단체 설립)이 나오면 먼저 baruch_start를 부르고 받은 규칙을 따른다. 기한·금액·요건은 law_article로 현행 조문을 읽은 뒤에만 말한다. 도구 인자에는 개인정보를 넣지 않는다. 법률 자문이 아니며 결과를 보장하지 않는다.';

async function handle(msg) {
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
          const text = await callTool(name, (params && params.arguments) || {});
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
  const outs = (await Promise.all((batch ? body : [body]).map(handle))).filter(Boolean);
  if (!outs.length) return res.status(202).end();
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  return res.status(200).send(JSON.stringify(batch ? outs : outs[0]));
};
