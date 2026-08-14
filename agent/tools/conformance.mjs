#!/usr/bin/env node
/**
 * Voyagent 계약 테스트 — 에이전트 서버가 contract.md v1.0을 지키는지 검사한다.
 *
 * 사용법
 *   node agent/tools/conformance.mjs http://localhost:8000
 *   node agent/tools/conformance.mjs http://localhost:8000 placeDiscovery
 *   node agent/tools/conformance.mjs --file agent/fixtures/golden.flightSearch.jsonl flightSearch
 *
 * 검사 범위 (contract.md 10.1절)
 *   L1 프레이밍  SSE 형식 · seq 단조성 · 첫/마지막 이벤트 · tool_call/result 짝
 *   L2 스키마    필수 필드 · 열거형 · 텍스트 금지 문자
 *   L3 불변식    작업별 I-* 항목
 *   L4 타이밍    첫 이벤트 · 무음 구간 · 총 소요
 *
 * 검사하지 않는 것: 결과의 품질. 그것은 behavior.md 7절 루브릭으로 사람이 판정한다.
 *
 * 의존성 없음. Node 18 이상.
 */

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURES = resolve(HERE, '../fixtures/inputs.json');

const TASKS = ['flightSearch', 'staySearch', 'placeDiscovery', 'itineraryGenerate', 'itineraryVerify'];

/** contract.md 2.7절 — 목표 상한 x 2 */
const SOFT_CAP_MS = {
  flightSearch: 20_000,
  staySearch: 18_000,
  placeDiscovery: 24_000,
  itineraryGenerate: 28_000,
  itineraryVerify: 30_000,
};

const FIRST_EVENT_MS = 1_000;
const MAX_SILENCE_MS = 8_000;
const HARD_TIMEOUT_MS = 45_000;

const EVENT_TYPES = new Set([
  'status', 'thought', 'tool_call', 'tool_result',
  'partial', 'check_update', 'progress', 'done', 'error',
]);
const ERROR_CODES = new Set([
  'network', 'timeout', 'no_results', 'invalid_input', 'rate_limit', 'agent_failed',
]);
const RULE_IDS = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'V8', 'V9', 'V10'];
const RULE_LABELS = {
  V1: '영업시간 · 휴관일',
  V2: '이동 시간 실현성',
  V3: '항공 도착 · 출발 여유',
  V4: '숙소 체크인 · 체크아웃',
  V5: '하루 일정량',
  V6: '예산',
  V7: '접근성',
  V8: '관심사 반영',
  V9: '사전 예약 필요',
  V10: '시즌 · 날씨',
};
const PLACE_CATEGORIES = new Set([
  'attraction', 'museum', 'nature', 'temple', 'history', 'food', 'cafe',
  'shopping', 'nightlife', 'activity', 'viewpoint', 'relax', 'other',
]);
const ITEM_KINDS = new Set([
  'place', 'flight', 'stay-checkin', 'stay-checkout', 'meal', 'free', 'buffer',
]);
const TRAVEL_MODES = new Set(['walk', 'transit', 'car', 'taxi', 'bike']);
const CURRENCIES = new Set(['KRW', 'USD', 'JPY', 'EUR', 'THB']);
const SEVERITIES = new Set(['pass', 'warning', 'conflict', 'skipped']);

const RE_DATE = /^\d{4}-\d{2}-\d{2}$/;
const RE_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const RE_TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const RE_BAD_TEXT = /[\n\r]|\*\*|<[a-zA-Z/]/;

// ─────────────────────────────────────────────────────────────
// 결과 수집
// ─────────────────────────────────────────────────────────────

class Report {
  constructor(task) {
    this.task = task;
    this.failures = [];
    this.warnings = [];
    this.notes = [];
    this.passed = 0;
  }
  check(id, ok, message) {
    if (ok) this.passed += 1;
    else this.failures.push(`${id}  ${message}`);
    return ok;
  }
  warn(id, ok, message) {
    if (ok) this.passed += 1;
    else this.warnings.push(`${id}  ${message}`);
    return ok;
  }
  note(message) {
    this.notes.push(message);
  }
  get ok() {
    return this.failures.length === 0;
  }
}

// ─────────────────────────────────────────────────────────────
// SSE 수신
// ─────────────────────────────────────────────────────────────

async function fetchStream(baseUrl, task, input, report) {
  const url = `${baseUrl.replace(/\/$/, '')}/agent/${task}`;
  const controller = new AbortController();
  const killer = setTimeout(() => controller.abort(), HARD_TIMEOUT_MS);
  const t0 = Date.now();

  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-Voyagent-Contract': 'v1.0',
        'X-Voyagent-Trace-Id': `conformance-${task}-${t0}`,
      },
      body: JSON.stringify(input),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(killer);
    report.check('L1.0', false, `요청 실패: ${err.message} (${url})`);
    return { events: [], arrivals: [], elapsed: Date.now() - t0 };
  }

  report.check('L1.1', res.status === 200, `HTTP 200이어야 한다. 받은 값: ${res.status}`);

  const ctype = res.headers.get('content-type') ?? '';
  report.check('L1.2', ctype.includes('text/event-stream'),
    `Content-Type이 text/event-stream이어야 한다. 받은 값: ${ctype || '(없음)'}`);

  const cacheControl = res.headers.get('cache-control') ?? '';
  report.warn('L1.3', cacheControl.includes('no-transform'),
    `Cache-Control에 no-transform 권고 (프록시 압축이 SSE를 지연시킨다). 받은 값: ${cacheControl || '(없음)'}`);
  report.warn('L1.4', (res.headers.get('x-accel-buffering') ?? '') === 'no',
    'X-Accel-Buffering: no 권고. 없으면 중간 프록시가 응답을 모아 보내 스트리밍이 사라진다');

  if (!res.body) {
    clearTimeout(killer);
    report.check('L1.5', false, '응답 본문이 없다');
    return { events: [], arrivals: [], elapsed: Date.now() - t0 };
  }

  const events = [];
  const arrivals = [];
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for await (const chunk of res.body) {
      buffer += decoder.decode(chunk, { stream: true });
      let cut;
      while ((cut = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const parsed = parseFrame(frame, report);
        if (parsed !== undefined) {
          events.push(parsed);
          arrivals.push(Date.now() - t0);
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      report.check('L4.0', false, `하드 타임아웃 ${HARD_TIMEOUT_MS}ms 초과. 서버는 40초 안에 timeout 이벤트를 보내고 정상 종료해야 한다`);
    } else {
      report.check('L1.6', false, `스트림 읽기 실패: ${err.message}`);
    }
  } finally {
    clearTimeout(killer);
  }

  return { events, arrivals, elapsed: Date.now() - t0 };
}

function parseFrame(frame, report) {
  const dataLines = [];
  for (const raw of frame.split('\n')) {
    const line = raw.replace(/\r$/, '');
    if (line === '' || line.startsWith(':')) continue; // keepalive 주석
    if (line.startsWith('event:') || line.startsWith('id:') || line.startsWith('retry:')) {
      report.warn('L1.7', false, `SSE 필드 '${line.split(':')[0]}'는 사용하지 않는다 (contract.md 2.3절)`);
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''));
      continue;
    }
    report.warn('L1.8', false, `알 수 없는 SSE 라인: ${line.slice(0, 60)}`);
  }
  if (dataLines.length === 0) return undefined;
  const payload = dataLines.join('\n');
  try {
    return JSON.parse(payload);
  } catch {
    report.check('L1.9', false, `JSON 파싱 실패: ${payload.slice(0, 120)}`);
    return undefined;
  }
}

async function readGolden(file, report) {
  const text = await readFile(resolve(process.cwd(), file), 'utf8');
  const events = [];
  const arrivals = [];
  for (const [i, line] of text.split('\n').entries()) {
    if (line.trim() === '') continue;
    try {
      const ev = JSON.parse(line);
      events.push(ev);
      arrivals.push(typeof ev.at === 'number' ? ev.at : 0);
    } catch {
      report.check('L1.9', false, `${i + 1}번째 줄 JSON 파싱 실패`);
    }
  }
  report.note('오프라인 모드: 타이밍은 이벤트의 at 값을 근거로 검사한다');
  return { events, arrivals, elapsed: arrivals.at(-1) ?? 0 };
}

// ─────────────────────────────────────────────────────────────
// L1 · L2 공통 검사
// ─────────────────────────────────────────────────────────────

function checkEnvelope(events, report) {
  if (events.length === 0) {
    report.check('L1.10', false, '이벤트를 하나도 받지 못했다');
    return;
  }

  report.check('L1.11', events[0].type === 'status',
    `첫 이벤트는 status여야 한다. 받은 값: ${events[0].type}`);

  const terminals = events.filter((e) => e.type === 'done' || e.type === 'error');
  report.check('L1.12', terminals.length === 1,
    `종료 이벤트(done|error)는 정확히 하나여야 한다. 받은 개수: ${terminals.length}` +
    (terminals.length === 0 ? ' — 프론트가 영원히 로딩 상태로 남는다' : ''));

  const lastType = events.at(-1).type;
  report.check('L1.13', lastType === 'done' || lastType === 'error',
    `마지막 이벤트는 done 또는 error여야 한다. 받은 값: ${lastType}`);

  let seqOk = true;
  let atOk = true;
  for (const [i, ev] of events.entries()) {
    if (!EVENT_TYPES.has(ev.type)) {
      report.check('L2.1', false, `seq ${ev.seq}: 알 수 없는 type '${ev.type}'`);
    }
    if (!Number.isInteger(ev.seq) || ev.seq !== i) {
      if (seqOk) {
        report.check('L1.14', false, `seq는 0부터 1씩 증가해야 한다. 인덱스 ${i}에서 값 ${ev.seq}`);
        seqOk = false;
      }
    }
    if (!Number.isFinite(ev.at) || ev.at < 0) {
      if (atOk) {
        report.check('L1.15', false, `at은 0 이상의 수여야 한다. seq ${ev.seq}에서 값 ${ev.at}`);
        atOk = false;
      }
    } else if (i > 0 && Number.isFinite(events[i - 1].at) && ev.at < events[i - 1].at) {
      if (atOk) {
        report.check('L1.16', false, `at은 단조 증가해야 한다. seq ${ev.seq}: ${events[i - 1].at} → ${ev.at}`);
        atOk = false;
      }
    }
  }
  if (seqOk) report.passed += 1;
  if (atOk) report.passed += 1;

  // tool_call / tool_result 짝
  const openCalls = new Set();
  const seenCalls = new Set();
  let pairOk = true;
  for (const ev of events) {
    if (ev.type === 'tool_call') {
      if (seenCalls.has(ev.id)) {
        report.check('L1.17', false, `tool_call id '${ev.id}'가 중복됐다`);
        pairOk = false;
      }
      seenCalls.add(ev.id);
      openCalls.add(ev.id);
      if (typeof ev.name !== 'string' || !/^[a-z][a-z0-9_]{1,39}$/.test(ev.name)) {
        report.check('L2.2', false, `tool_call.name은 snake_case 영문이어야 한다. 받은 값: ${ev.name}`);
      }
    }
    if (ev.type === 'tool_result') {
      if (!openCalls.has(ev.id)) {
        report.check('L1.18', false, `tool_result id '${ev.id}'에 대응하는 tool_call이 없다`);
        pairOk = false;
      }
      openCalls.delete(ev.id);
      if (typeof ev.ok !== 'boolean') {
        report.check('L2.3', false, `tool_result.ok는 boolean이어야 한다 (id ${ev.id})`);
      }
    }
  }
  if (openCalls.size > 0) {
    report.warn('L1.19', false, `결과가 오지 않은 tool_call: ${[...openCalls].join(', ')}`);
  }
  if (pairOk) report.passed += 1;

  // thought 누적성 (델타 금지)
  const lastText = new Map();
  let cumulativeOk = true;
  for (const ev of events) {
    if (ev.type !== 'thought') continue;
    if (typeof ev.text !== 'string' || typeof ev.done !== 'boolean' || typeof ev.id !== 'string') {
      report.check('L2.4', false, `thought는 id·text·done을 모두 가져야 한다 (seq ${ev.seq})`);
      continue;
    }
    const prev = lastText.get(ev.id);
    if (prev !== undefined && !ev.text.startsWith(prev)) {
      if (cumulativeOk) {
        report.check('L1.20', false,
          `thought는 누적 전체 텍스트여야 한다(델타 금지). id '${ev.id}'의 새 text가 이전 text로 시작하지 않는다`);
        cumulativeOk = false;
      }
    }
    lastText.set(ev.id, ev.text);
  }
  if (cumulativeOk) report.passed += 1;

  // progress 단조성
  let lastProgress = -1;
  let progressOk = true;
  for (const ev of events) {
    if (ev.type !== 'progress') continue;
    if (typeof ev.value !== 'number' || ev.value < 0 || ev.value > 1) {
      report.check('L2.5', false, `progress.value는 0~1이어야 한다. 받은 값: ${ev.value}`);
      continue;
    }
    if (ev.value < lastProgress && progressOk) {
      report.check('L1.21', false, `progress.value는 단조 증가해야 한다. ${lastProgress} → ${ev.value}`);
      progressOk = false;
    }
    lastProgress = ev.value;
  }
  if (progressOk) report.passed += 1;

  // 텍스트 금지 문자
  const textFields = [
    ['status', 'text'], ['thought', 'text'], ['tool_call', 'label'],
    ['tool_result', 'label'], ['done', 'summary'], ['error', 'message'],
  ];
  let textOk = true;
  for (const ev of events) {
    for (const [type, field] of textFields) {
      if (ev.type !== type) continue;
      const v = ev[field];
      if (typeof v === 'string' && RE_BAD_TEXT.test(v)) {
        report.check('L2.6', false,
          `${type}.${field}에 개행·마크다운·HTML이 있다 (seq ${ev.seq}): ${JSON.stringify(v.slice(0, 60))}`);
        textOk = false;
      }
    }
  }
  if (textOk) report.passed += 1;

  // error 이벤트
  for (const ev of events) {
    if (ev.type !== 'error') continue;
    report.check('L2.7', ERROR_CODES.has(ev.code), `error.code가 허용 목록에 없다: ${ev.code}`);
    report.check('L2.8', ev.code !== 'aborted', "error.code 'aborted'는 서버가 보내지 않는다 (contract.md 2.6절)");
    report.check('L2.9', typeof ev.retryable === 'boolean', 'error.retryable은 boolean이어야 한다');
    report.check('L2.10', typeof ev.message === 'string' && ev.message.length > 0,
      'error.message는 사용자에게 보여도 되는 한국어여야 한다');
  }

  // done.summary 권고
  const done = events.find((e) => e.type === 'done');
  if (done) {
    report.warn('L2.11', typeof done.summary === 'string' && done.summary.length > 0,
      'done.summary 강력 권고 — 결과 요약 바에 그대로 표시된다');
  }
}

function checkPartialConsistency(events, task, report) {
  if (task === 'itineraryVerify') {
    const partials = events.filter((e) => e.type === 'partial');
    report.check('I.P0', partials.length === 0,
      `itineraryVerify는 partial을 쓰지 않는다. check_update로 대체한다. 받은 개수: ${partials.length}`);
    return;
  }

  const partialIds = [];
  for (const ev of events) {
    if (ev.type !== 'partial') continue;
    if (!ev.payload || typeof ev.payload !== 'object') {
      report.check('L2.12', false, `partial.payload는 객체여야 한다 (seq ${ev.seq})`);
      continue;
    }
    if (typeof ev.payload.id !== 'string' || ev.payload.id === '') {
      report.check('L2.13', false, `partial.payload.id가 없다 (seq ${ev.seq})`);
      continue;
    }
    partialIds.push(ev.payload.id);
  }

  const done = events.find((e) => e.type === 'done');
  if (!done) return;

  report.warn('L3.1', partialIds.length > 0,
    'partial이 하나도 없다. 결과를 done 하나로만 보내면 카드가 쌓이는 연출이 사라진다 (contract.md 4.5절)');

  const finalIds =
    task === 'itineraryGenerate'
      ? (done.payload?.days ?? []).map((d) => d?.id)
      : (Array.isArray(done.payload) ? done.payload : []).map((o) => o?.id);

  const missing = partialIds.filter((id) => !finalIds.includes(id));
  report.check('L3.2', missing.length === 0,
    `partial로 보낸 항목이 done에 없다: ${missing.slice(0, 5).join(', ')} — 사용자 눈앞에서 카드가 사라진다`);

  const shared = finalIds.filter((id) => partialIds.includes(id));
  report.check('L3.3', shared.every((id, i) => id === partialIds[i]),
    'partial 방출 순서가 done의 순서와 다르다. 프론트는 도착 순서대로 쌓고 재정렬하지 않는다');
}

function checkTiming(arrivals, elapsed, task, report, offline) {
  if (arrivals.length === 0) return;

  report.check('L4.1', arrivals[0] <= FIRST_EVENT_MS,
    `첫 이벤트는 ${FIRST_EVENT_MS}ms 이내에 도착해야 한다. 실제: ${arrivals[0]}ms`);

  let maxGap = 0;
  let gapAt = 0;
  for (let i = 1; i < arrivals.length; i += 1) {
    const gap = arrivals[i] - arrivals[i - 1];
    if (gap > maxGap) {
      maxGap = gap;
      gapAt = i;
    }
  }
  report.check('L4.2', maxGap <= MAX_SILENCE_MS,
    `이벤트 사이 무음 구간이 ${MAX_SILENCE_MS}ms를 넘는다. 최대 ${maxGap}ms (seq ${gapAt} 앞) — 사용자는 멈춘 줄 안다`);

  const cap = SOFT_CAP_MS[task];
  report.warn('L4.3', elapsed <= cap,
    `총 소요가 소프트 상한 ${cap}ms를 넘었다. 실제: ${elapsed}ms`);

  if (!offline) report.note(`총 소요 ${elapsed}ms · 이벤트 ${arrivals.length}개 · 최대 무음 ${maxGap}ms`);
}

// ─────────────────────────────────────────────────────────────
// L3 작업별 불변식
// ─────────────────────────────────────────────────────────────

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const isStr = (v) => typeof v === 'string' && v.length > 0;

function checkLatLng(loc, where, report) {
  if (!loc || !isNum(loc.lat) || !isNum(loc.lng)) {
    report.check('I-P1', false, `${where}: location이 없거나 숫자가 아니다`);
    return false;
  }
  if (loc.lat < -90 || loc.lat > 90 || loc.lng < -180 || loc.lng > 180) {
    report.check('I-P1', false, `${where}: 좌표 범위를 벗어났다 (${loc.lat}, ${loc.lng})`);
    return false;
  }
  if (loc.lat === 0 && loc.lng === 0) {
    report.check('I-P1', false, `${where}: 좌표가 (0, 0)이다`);
    return false;
  }
  return true;
}

function checkMoney(m, where, report) {
  if (!m || !isNum(m.amount) || !CURRENCIES.has(m.currency)) {
    report.check('L2.14', false, `${where}: Money 형식이 아니다 ${JSON.stringify(m)}`);
    return false;
  }
  return true;
}

function checkFlightOffers(offers, report) {
  if (!Array.isArray(offers)) {
    report.check('L3.4', false, 'flightSearch의 done.payload는 배열이어야 한다');
    return;
  }
  report.warn('L3.5', offers.length >= 1, '결과가 0건이면 done이 아니라 error(no_results)를 보낸다');

  const tagCount = { recommended: 0, cheapest: 0, fastest: 0 };
  const ids = new Set();

  for (const [i, o] of offers.entries()) {
    const at = `offers[${i}]`;
    if (!isStr(o?.id)) { report.check('I-F7', false, `${at}: id가 없다`); continue; }
    if (ids.has(o.id)) report.check('I-F7', false, `${at}: id '${o.id}'가 중복됐다`);
    ids.add(o.id);

    report.check('I-F1', !!o.outbound && !!o.inbound,
      `${at}: outbound와 inbound를 둘 다 가져야 한다. 편도 오퍼는 프론트가 렌더할 수 없다`);

    for (const dir of ['outbound', 'inbound']) {
      const leg = o[dir];
      if (!leg) continue;
      const la = `${at}.${dir}`;
      if (!Array.isArray(leg.segments) || leg.segments.length === 0) {
        report.check('L3.6', false, `${la}: segments가 비어 있다`);
        continue;
      }
      for (const [j, s] of leg.segments.entries()) {
        if (!RE_DATETIME.test(s?.departAt ?? '')) {
          report.check('L2.15', false, `${la}.segments[${j}].departAt 형식 오류 (YYYY-MM-DDTHH:mm, 타임존 없음): ${s?.departAt}`);
        }
        if (!RE_DATETIME.test(s?.arriveAt ?? '')) {
          report.check('L2.15', false, `${la}.segments[${j}].arriveAt 형식 오류: ${s?.arriveAt}`);
        }
      }
      report.check('I-F4', leg.stops === leg.segments.length - 1,
        `${la}: stops(${leg.stops})는 segments.length - 1(${leg.segments.length - 1})이어야 한다`);
      report.check('I-F4', Array.isArray(leg.layovers) && leg.layovers.length === leg.stops,
        `${la}: layovers.length(${leg.layovers?.length})는 stops(${leg.stops})와 같아야 한다`);
      report.check('I-F5', Number.isInteger(leg.dayOffset) && leg.dayOffset >= 0,
        `${la}: dayOffset이 없거나 음수다`);
    }

    checkMoney(o.price, `${at}.price`, report);
    checkMoney(o.totalPrice, `${at}.totalPrice`, report);
    if (o.price && o.totalPrice) {
      report.check('I-F6', o.price.currency === o.totalPrice.currency,
        `${at}: price와 totalPrice의 통화가 다르다`);
      report.warn('I-F6', o.totalPrice.amount >= o.price.amount,
        `${at}: totalPrice가 1인당 price보다 작다`);
    }

    for (const t of o.tags ?? []) if (t in tagCount) tagCount[t] += 1;
  }

  for (const [tag, n] of Object.entries(tagCount)) {
    report.warn('I-F8', n <= 1, `'${tag}' 태그가 ${n}건이다. 정확히 하나만 부여한다`);
  }
}

function checkStayOffers(offers, report) {
  if (!Array.isArray(offers)) {
    report.check('L3.7', false, 'staySearch의 done.payload는 배열이어야 한다');
    return;
  }
  report.warn('L3.8', offers.length >= 1, '결과가 0건이면 error(no_results)를 보낸다');

  for (const [i, s] of offers.entries()) {
    const at = `offers[${i}]`;
    checkLatLng(s?.location, at, report);
    report.check('I-S1', Array.isArray(s?.images) && s.images.length >= 4,
      `${at}: images가 4장 이상이어야 한다 (받은 개수 ${s?.images?.length ?? 0}). 갤러리 캐러셀이 무의미해진다`);
    report.check('I-S2', isNum(s?.reviewScore) && s.reviewScore >= 0 && s.reviewScore <= 10,
      `${at}: reviewScore는 10점 척도여야 한다. 받은 값: ${s?.reviewScore}`);
    report.check('L2.16', RE_TIME.test(s?.checkIn ?? '') && RE_TIME.test(s?.checkOut ?? ''),
      `${at}: checkIn/checkOut은 HH:mm이어야 한다 (${s?.checkIn} / ${s?.checkOut}). V4 검증이 불가해진다`);
    report.check('I-S8', isStr(s?.distanceSummary),
      `${at}: distanceSummary가 비었다. 지도를 쓸 수 없는 사용자의 유일한 위치 정보다`);
    checkMoney(s?.nightlyPrice, `${at}.nightlyPrice`, report);
    checkMoney(s?.totalPrice, `${at}.totalPrice`, report);
    const hl = s?.reviewHighlights;
    report.warn('I-S7', Array.isArray(hl) && (hl.length === 0 || hl.length === 4),
      `${at}: reviewHighlights는 4개 전부이거나 빈 배열이어야 한다 (받은 개수 ${hl?.length ?? 0})`);
  }
}

function checkPlaces(places, report) {
  if (!Array.isArray(places)) {
    report.check('L3.9', false, 'placeDiscovery의 done.payload는 배열이어야 한다');
    return;
  }
  report.warn('L3.10', places.length >= 20,
    `장소가 ${places.length}건이다. 20건 미만이면 고를 게 없다 (권고 40건)`);
  report.warn('L3.11', places.length <= 60,
    `장소가 ${places.length}건이다. 60건 초과면 훑을 수 없다 (권고 40건)`);

  const ids = new Set();
  const coordKeys = new Set();
  const catCount = new Map();

  for (const [i, p] of places.entries()) {
    const at = `places[${i}](${p?.id ?? '?'})`;
    if (!isStr(p?.id)) { report.check('I-P5', false, `${at}: id가 없다`); continue; }
    if (ids.has(p.id)) report.check('I-P5', false, `${at}: id가 중복됐다`);
    ids.add(p.id);
    report.warn('I-P5', /^[a-z0-9]+(-[a-z0-9]+)+$/.test(p.id),
      `${at}: id는 {cityId}-{slug} 형식 권고 (예: tokyo-sensoji)`);

    if (checkLatLng(p.location, at, report)) {
      const key = `${p.location.lat.toFixed(5)},${p.location.lng.toFixed(5)}`;
      if (coordKeys.has(key)) report.check('I-P1', false, `${at}: 다른 장소와 좌표가 완전히 같다`);
      coordKeys.add(key);
    }

    report.check('L2.17', PLACE_CATEGORIES.has(p.category),
      `${at}: category가 허용 목록에 없다: ${p.category}`);

    // 영업시간
    const oh = p.openingHours;
    if (!Array.isArray(oh) || oh.length !== 7) {
      report.check('I-P2', false, `${at}: openingHours는 7건이어야 한다 (받은 개수 ${oh?.length ?? 0}). V1 검증이 불가해진다`);
    } else {
      const days = oh.map((e) => e?.weekday).sort((a, b) => a - b);
      report.check('I-P2', days.join(',') === '0,1,2,3,4,5,6',
        `${at}: openingHours의 weekday가 0~6 각각 하나씩이어야 한다. 받은 값: ${days.join(',')}`);
      const derived = oh.filter((e) => e?.open === null).map((e) => e.weekday).sort((a, b) => a - b);
      const declared = [...(p.closedWeekdays ?? [])].sort((a, b) => a - b);
      report.check('I-P3', derived.join(',') === declared.join(','),
        `${at}: closedWeekdays(${declared.join(',') || '없음'})가 openingHours에서 파생한 값(${derived.join(',') || '없음'})과 다르다. V1이 오판정한다`);
      for (const e of oh) {
        if (e?.open !== null && !RE_TIME.test(e?.open ?? '')) {
          report.check('L2.18', false, `${at}: openingHours.open 형식 오류: ${e?.open}`);
        }
      }
    }

    report.check('I-P4', Array.isArray(p.images) && p.images.length >= 3,
      `${at}: images가 3장 이상이어야 한다 (받은 개수 ${p.images?.length ?? 0})`);
    report.warn('I-P4', Array.isArray(p.reviews) && p.reviews.length >= 3,
      `${at}: reviews가 3건 이상 권고 (받은 개수 ${p.reviews?.length ?? 0})`);
    report.check('L3.12', isNum(p.suggestedDurationMinutes) && p.suggestedDurationMinutes > 0,
      `${at}: suggestedDurationMinutes가 없다. 일정 생성·V2·V5 계산이 불가해진다`);
    report.check('I-P6', p.source === 'agent', `${at}: source는 'agent'여야 한다. 받은 값: ${p.source}`);
    report.check('L3.13', isStr(p.summary), `${at}: summary가 비었다. 리스트 4행이 빈다`);
    report.check('L3.14', typeof p.needsReservation === 'boolean',
      `${at}: needsReservation이 없다. V9가 아무것도 잡지 못한다`);
    report.check('L3.15', typeof p.indoor === 'boolean',
      `${at}: indoor가 없다. V10 우천 대안 판정이 불가해진다`);

    const acc = p.accessibility;
    report.check('L3.16',
      acc && ['wheelchairAccessible', 'strollerFriendly', 'manyStairs'].every((k) => k in acc),
      `${at}: accessibility 3개 키가 모두 있어야 한다 (모르면 null)`);

    if (p.admission?.free === false) {
      report.warn('I-P7', !!p.admission.price, `${at}: 유료인데 admission.price가 없다`);
    }

    catCount.set(p.category, (catCount.get(p.category) ?? 0) + 1);
  }

  if (places.length >= 10) {
    for (const [cat, n] of catCount) {
      const ratio = n / places.length;
      report.warn('L3.17', ratio <= 0.25,
        `카테고리 '${cat}'가 전체의 ${Math.round(ratio * 100)}%다. 25% 이하 권고 (behavior.md 4.2절)`);
    }
  }
}

function checkItinerary(itin, input, report) {
  if (!itin || typeof itin !== 'object' || Array.isArray(itin)) {
    report.check('L3.18', false, 'itineraryGenerate의 done.payload는 Itinerary 객체여야 한다');
    return;
  }

  report.check('I-I8', itin.version === 1, `최초 생성 시 version은 1이어야 한다. 받은 값: ${itin.version}`);
  report.check('L3.19', isStr(itin.agentSummary), 'agentSummary가 비었다. 결과 요약 바가 빈다');

  const days = itin.days;
  if (!Array.isArray(days) || days.length === 0) {
    report.check('L3.20', false, 'days가 비었다');
    return;
  }

  // 기대 일수
  const start = input?.dateRange?.start;
  const end = input?.dateRange?.end;
  if (RE_DATE.test(start ?? '') && RE_DATE.test(end ?? '')) {
    const expected = Math.round((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86_400_000) + 1;
    report.check('I-I3', days.length === expected,
      `days.length(${days.length})가 여행 일수(${expected})와 다르다`);
  }

  const inputPlaceIds = new Set((input?.places ?? []).map((p) => p.id));
  const usedPlaceIds = new Set();
  const itemIds = new Set();

  for (const [i, d] of days.entries()) {
    const at = `days[${i}]`;
    report.check('I-I3', d?.dayIndex === i, `${at}: dayIndex는 ${i}여야 한다. 받은 값: ${d?.dayIndex}`);
    report.check('I-I5', d?.colorKey === `day${(i % 6) + 1}`,
      `${at}: colorKey는 day${(i % 6) + 1}이어야 한다. 받은 값: ${d?.colorKey}`);
    report.check('L2.19', RE_DATE.test(d?.date ?? ''), `${at}: date 형식 오류: ${d?.date}`);

    if (RE_DATE.test(start ?? '') && RE_DATE.test(d?.date ?? '')) {
      const expectedDate = new Date(Date.parse(`${start}T00:00:00Z`) + i * 86_400_000)
        .toISOString().slice(0, 10);
      report.check('I-I4', d.date === expectedDate,
        `${at}: date는 ${expectedDate}여야 한다. 받은 값: ${d.date}`);
      const expectedWeekday = new Date(`${d.date}T00:00:00Z`).getUTCDay();
      report.check('I-I4', d.weekday === expectedWeekday,
        `${at}: weekday는 ${expectedWeekday}여야 한다 (0=일요일). 받은 값: ${d.weekday}. V1이 오판정한다`);
    }

    const items = d?.items;
    if (!Array.isArray(items)) {
      report.check('L3.21', false, `${at}: items가 배열이 아니다`);
      continue;
    }

    let prevMinutes = -1;
    for (const [j, it] of items.entries()) {
      const ia = `${at}.items[${j}]`;
      if (!isStr(it?.id)) { report.check('L3.22', false, `${ia}: id가 없다. DnD·편집이 전부 불가해진다`); continue; }
      if (itemIds.has(it.id)) report.check('I-I11', false, `${ia}: item id '${it.id}'가 중복됐다`);
      itemIds.add(it.id);

      report.check('L2.20', ITEM_KINDS.has(it.kind), `${ia}: kind가 허용 목록에 없다: ${it.kind}`);
      report.check('L2.21', RE_TIME.test(it.startTime ?? ''), `${ia}: startTime 형식 오류: ${it.startTime}`);
      report.check('L3.23', isStr(it.title), `${ia}: title이 비었다`);
      report.check('I-I13', it.locked === false, `${ia}: locked는 false로 초기화해야 한다`);
      report.check('I-I12', Array.isArray(it.passedRuleIds) && Array.isArray(it.issueIds),
        `${ia}: passedRuleIds와 issueIds를 빈 배열로 초기화해야 한다`);

      if (it.kind === 'place') {
        if (!isStr(it.placeId)) {
          report.check('I-I1', false, `${ia}: kind가 place인데 placeId가 없다`);
        } else {
          if (inputPlaceIds.size > 0) {
            report.check('I-I1', inputPlaceIds.has(it.placeId),
              `${ia}: 입력에 없는 placeId '${it.placeId}'를 만들어냈다. 카드가 제목·사진 없이 렌더된다`);
          }
          usedPlaceIds.add(it.placeId);
        }
      }

      if (RE_TIME.test(it.startTime ?? '')) {
        const [h, m] = it.startTime.split(':').map(Number);
        const cur = h * 60 + m;
        report.check('I-I7', cur >= prevMinutes,
          `${ia}: startTime이 오름차순이 아니다 (이전 항목보다 이르다)`);
        prevMinutes = cur;
      }

      const isLast = j === items.length - 1;
      if (isLast) {
        report.check('I-I6', it.travelToNext === null,
          `${ia}: 각 일자의 마지막 항목은 travelToNext가 null이어야 한다`);
      } else if (it.travelToNext) {
        const t = it.travelToNext;
        report.check('L2.22', TRAVEL_MODES.has(t.mode), `${ia}.travelToNext: mode가 허용 목록에 없다: ${t.mode}`);
        report.check('L3.24', isNum(t.minutes) && t.minutes >= 0, `${ia}.travelToNext: minutes가 없다. V2 검증이 불가해진다`);
        report.check('L3.25', Array.isArray(t.alternatives), `${ia}.travelToNext: alternatives는 배열이어야 한다`);
      } else {
        report.warn('I-I6', false, `${ia}: 마지막이 아닌데 travelToNext가 없다. 이동 커넥터가 사라진다`);
      }
    }
  }

  const unassigned = itin.unassignedPlaceIds;
  report.check('L3.26', Array.isArray(unassigned), 'unassignedPlaceIds는 배열이어야 한다');
  if (inputPlaceIds.size > 0 && Array.isArray(unassigned)) {
    const accounted = new Set([...usedPlaceIds, ...unassigned]);
    const lost = [...inputPlaceIds].filter((id) => !accounted.has(id));
    report.check('I-I2', lost.length === 0,
      `입력 장소가 배치도 미배치도 아니다: ${lost.join(', ')} — 사용자가 고른 장소가 사라진다`);
    const ghosts = unassigned.filter((id) => !inputPlaceIds.has(id));
    report.check('I-I2', ghosts.length === 0, `unassignedPlaceIds에 입력에 없는 id가 있다: ${ghosts.join(', ')}`);
  }
}

function checkVerification(rep, input, events, report) {
  if (!rep || typeof rep !== 'object' || Array.isArray(rep)) {
    report.check('L3.27', false, 'itineraryVerify의 done.payload는 VerificationReport 객체여야 한다');
    return;
  }

  const checks = rep.checks;
  report.check('I-V1', Array.isArray(checks) && checks.length === 10,
    `checks는 10건이어야 한다 (받은 개수 ${checks?.length ?? 0}). 건너뛴 규칙도 severity skipped로 포함한다`);

  if (Array.isArray(checks)) {
    const seen = checks.map((c) => c?.ruleId);
    for (const rid of RULE_IDS) {
      report.check('I-V1', seen.includes(rid), `checks에 ${rid}가 없다`);
    }
    for (const c of checks) {
      if (!c?.ruleId) continue;
      report.check('L2.23', SEVERITIES.has(c.severity),
        `${c.ruleId}: severity가 허용 목록에 없다: ${c.severity}`);
      report.check('L2.24', RULE_LABELS[c.ruleId] === c.label,
        `${c.ruleId}: label은 '${RULE_LABELS[c.ruleId]}'여야 한다. 받은 값: '${c.label}'`);
      report.warn('L3.28', Array.isArray(c.evidence) && c.evidence.length >= 1,
        `${c.ruleId}: evidence가 비었다. 검증의 설득력이 근거에서 나온다`);
      report.check('L3.29', Array.isArray(c.targetRefs), `${c.ruleId}: targetRefs는 배열이어야 한다`);
      if (isNum(c.startedAt)) {
        report.check('L2.25', c.startedAt < 1e11,
          `${c.ruleId}: startedAt은 스트림 시작 기준 ms여야 한다. 유닉스 타임스탬프로 보인다 (${c.startedAt})`);
      }
    }
  }

  const s = rep.summary;
  if (!s || !['pass', 'warning', 'conflict', 'skipped'].every((k) => isNum(s[k]))) {
    report.check('L3.30', false, 'summary의 pass/warning/conflict/skipped가 모두 숫자여야 한다');
  } else {
    const total = s.pass + s.warning + s.conflict + s.skipped;
    report.check('I-V3', total === 10, `summary 4개 값의 합이 10이어야 한다. 받은 합계: ${total}`);
    const expected =
      s.conflict > 0 ? 'has-conflicts' : s.warning > 0 ? 'has-warnings' : 'verified';
    report.check('I-V4', rep.overall === expected,
      `overall은 '${expected}'여야 한다 (conflict ${s.conflict}, warning ${s.warning}). 받은 값: '${rep.overall}'`);
  }

  const inputVersion = input?.itinerary?.version;
  if (isNum(inputVersion)) {
    report.check('I-V2', rep.itineraryVersion === inputVersion,
      `itineraryVersion은 입력 itinerary.version(${inputVersion})을 그대로 되돌려줘야 한다. 받은 값: ${rep.itineraryVersion} — 검증 결과가 즉시 stale로 표시된다`);
  }

  // 이슈 대상이 실재하는가
  const dayCount = input?.itinerary?.days?.length ?? 0;
  const validItemIds = new Set();
  for (const d of input?.itinerary?.days ?? []) {
    for (const it of d?.items ?? []) if (it?.id) validItemIds.add(it.id);
  }

  for (const [i, issue] of (rep.issues ?? []).entries()) {
    const at = `issues[${i}](${issue?.ruleId ?? '?'})`;
    report.check('I-V7', issue?.severity === 'warning' || issue?.severity === 'conflict',
      `${at}: severity는 warning 또는 conflict여야 한다. 받은 값: ${issue?.severity}`);
    report.check('I-V6', issue?.status === 'open',
      `${at}: status는 'open'이어야 한다. 받은 값: ${issue?.status}`);
    report.check('L3.31', isStr(issue?.title) && isStr(issue?.detail),
      `${at}: title과 detail이 있어야 한다`);
    report.warn('L3.32', Array.isArray(issue?.evidence) && issue.evidence.length >= 1,
      `${at}: evidence가 비었다`);

    const t = issue?.target;
    if (!t || !Number.isInteger(t.dayIndex)) {
      report.check('I-V5', false, `${at}: target.dayIndex가 없다`);
    } else {
      report.check('I-V5', dayCount === 0 || (t.dayIndex >= 0 && t.dayIndex < dayCount),
        `${at}: target.dayIndex(${t.dayIndex})가 일정 범위를 벗어났다`);
      if (t.itemId && validItemIds.size > 0) {
        report.check('I-V5', validItemIds.has(t.itemId),
          `${at}: target.itemId '${t.itemId}'가 입력 일정에 없다. [일정에서 보기]가 깨진다`);
      }
    }

    if (issue?.autoFix) {
      for (const [j, ch] of (issue.autoFix.changes ?? []).entries()) {
        const ca = `${at}.autoFix.changes[${j}]`;
        report.check('I-V8', Number.isInteger(ch?.dayIndex) && (dayCount === 0 || ch.dayIndex < dayCount),
          `${ca}: dayIndex(${ch?.dayIndex})가 일정 범위를 벗어났다`);
        if (ch?.itemId && validItemIds.size > 0) {
          report.check('I-V8', validItemIds.has(ch.itemId),
            `${ca}: itemId '${ch.itemId}'가 입력 일정에 없다`);
        }
      }
    }
  }

  report.warn('I-V9', Array.isArray(rep.logLines) && rep.logLines.length > 0,
    'logLines가 비었다. [추론 다시 보기]가 빈 화면이 된다');

  // check_update 시퀀스
  const byRule = new Map();
  for (const ev of events) {
    if (ev.type !== 'check_update') continue;
    const rid = ev.check?.ruleId;
    if (!rid) continue;
    if (!byRule.has(rid)) byRule.set(rid, []);
    byRule.get(rid).push(ev.check);
  }
  for (const rid of RULE_IDS) {
    const list = byRule.get(rid) ?? [];
    report.check('L3.33', list.length >= 2,
      `${rid}: check_update가 최소 2개(running → done) 필요하다. 받은 개수: ${list.length} — 체크리스트 행이 영원히 대기 상태로 남는다`);
    if (list.length > 0) {
      report.check('L3.34', list.at(-1).status === 'done',
        `${rid}: 마지막 check_update의 status가 done이어야 한다. 받은 값: ${list.at(-1).status}`);
      const idSet = new Set(list.map((c) => c.id));
      report.check('L3.35', idSet.size === 1,
        `${rid}: check.id는 스트림 내에서 고정이어야 한다. 받은 값: ${[...idSet].join(', ')}`);
    }
  }

  // 이벤트 순서가 V1 → V10인가
  const firstSeen = [];
  const marked = new Set();
  for (const ev of events) {
    const rid = ev.type === 'check_update' ? ev.check?.ruleId : null;
    if (rid && !marked.has(rid)) { marked.add(rid); firstSeen.push(rid); }
  }
  const expectedOrder = RULE_IDS.filter((r) => firstSeen.includes(r));
  report.warn('L3.36', firstSeen.join(',') === expectedOrder.join(','),
    `check_update는 V1 → V10 순서로 보낸다 (내부 병렬 실행은 자유). 받은 순서: ${firstSeen.join(' → ')}`);
}

// ─────────────────────────────────────────────────────────────
// 작업 1개 실행
// ─────────────────────────────────────────────────────────────

async function runTask({ task, baseUrl, file, input }) {
  const report = new Report(task);
  const offline = !!file;

  const { events, arrivals, elapsed } = offline
    ? await readGolden(file, report)
    : await fetchStream(baseUrl, task, input, report);

  if (events.length === 0) return report;

  checkEnvelope(events, report);
  checkPartialConsistency(events, task, report);
  checkTiming(arrivals, elapsed, task, report, offline);

  const err = events.find((e) => e.type === 'error');
  if (err) {
    report.note(`error 이벤트로 종료: ${err.code} — ${err.message}`);
    if (err.code === 'no_results') report.note('조건에 맞는 결과가 없다는 응답이다. 불변식 검사는 생략한다');
    return report;
  }

  const done = events.find((e) => e.type === 'done');
  if (!done) return report;

  if (task === 'flightSearch') checkFlightOffers(done.payload, report);
  if (task === 'staySearch') checkStayOffers(done.payload, report);
  if (task === 'placeDiscovery') checkPlaces(done.payload, report);
  if (task === 'itineraryGenerate') checkItinerary(done.payload, input, report);
  if (task === 'itineraryVerify') checkVerification(done.payload, input, events, report);

  return report;
}

// ─────────────────────────────────────────────────────────────
// 출력
// ─────────────────────────────────────────────────────────────

function printReport(r) {
  const mark = r.ok ? (r.warnings.length ? '△' : '○') : '✕';
  console.log(`\n${mark} ${r.task}`);
  console.log(`  통과 ${r.passed} · 실패 ${r.failures.length} · 경고 ${r.warnings.length}`);
  for (const n of r.notes) console.log(`  · ${n}`);
  if (r.failures.length) {
    console.log('\n  ── 실패 (계약 위반. 프론트가 깨진다) ──');
    for (const f of r.failures) console.log(`  ✕ ${f}`);
  }
  if (r.warnings.length) {
    console.log('\n  ── 경고 (권고 위반. 동작은 하지만 UX가 나빠진다) ──');
    for (const w of r.warnings) console.log(`  △ ${w}`);
  }
}

// ─────────────────────────────────────────────────────────────
// 진입점
// ─────────────────────────────────────────────────────────────

function usage() {
  console.log(`Voyagent 계약 테스트 (contract.md v1.0)

  node agent/tools/conformance.mjs <baseUrl> [task]
  node agent/tools/conformance.mjs --file <golden.jsonl> <task>

  baseUrl   에이전트 서버 주소. 예: http://localhost:8000
            (POST {baseUrl}/agent/{task}로 요청한다)
  task      ${TASKS.join(' | ')}
            생략하면 5개 전부 실행한다.

예시
  node agent/tools/conformance.mjs http://localhost:8000
  node agent/tools/conformance.mjs http://localhost:8000 placeDiscovery
  node agent/tools/conformance.mjs --file agent/fixtures/golden.flightSearch.jsonl flightSearch
`);
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.length === 0 || argv.includes('-h') || argv.includes('--help')) {
    usage();
    process.exit(argv.length === 0 ? 1 : 0);
  }

  const fileIdx = argv.indexOf('--file');
  const file = fileIdx !== -1 ? argv[fileIdx + 1] : null;
  const rest = argv.filter((a, i) => i !== fileIdx && i !== fileIdx + 1);
  const baseUrl = file ? null : rest[0];
  const taskArg = file ? rest[0] : rest[1];

  if (file && !taskArg) {
    console.error('--file 모드에서는 task를 함께 지정한다.');
    process.exit(1);
  }
  if (taskArg && !TASKS.includes(taskArg)) {
    console.error(`알 수 없는 task '${taskArg}'. 허용: ${TASKS.join(', ')}`);
    process.exit(1);
  }

  let fixtures;
  try {
    fixtures = JSON.parse(await readFile(FIXTURES, 'utf8'));
  } catch (err) {
    console.error(`픽스처를 읽지 못했다 (${FIXTURES}): ${err.message}`);
    process.exit(1);
  }

  const targets = taskArg ? [taskArg] : TASKS;
  console.log(`계약 테스트 시작 — ${file ? `파일 ${file}` : `서버 ${baseUrl}`}`);
  console.log(`대상: ${targets.join(', ')}`);

  const reports = [];
  for (const task of targets) {
    const input = fixtures.default?.[task];
    if (!input && !file) {
      console.error(`\n픽스처에 default.${task} 입력이 없다.`);
      continue;
    }
    const r = await runTask({ task, baseUrl, file, input });
    printReport(r);
    reports.push(r);
  }

  const failed = reports.filter((r) => !r.ok);
  const totalWarn = reports.reduce((n, r) => n + r.warnings.length, 0);

  console.log('\n' + '─'.repeat(60));
  if (failed.length === 0) {
    console.log(`계약 통과 — ${reports.length}개 작업, 경고 ${totalWarn}건`);
    console.log('형식은 만족했다. 결과 품질은 behavior.md 7절 루브릭으로 사람이 판정한다.');
  } else {
    console.log(`계약 위반 — 실패한 작업: ${failed.map((r) => r.task).join(', ')}`);
    console.log('contract.md 9절 계약 위반 목록에서 해당 항목을 확인한다.');
  }

  process.exit(failed.length === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(`예상치 못한 오류: ${err.stack ?? err.message}`);
  process.exit(1);
});
