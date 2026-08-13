#!/usr/bin/env node
/**
 * Voyagent handoff contract validator.
 *
 * Validates the two canonical boundaries:
 *   Search Agent -> Plan Agent
 *   Plan Agent   -> Verification Agent
 *
 * Usage: node agent/tools/conformance.mjs
 * Requires Node.js 18+ and has no package dependencies.
 */

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const CONTRACTS = [
  {
    name: 'search-to-plan',
    schemaPath: resolve(HERE, '../schemas/search-to-plan.schema.json'),
    fixturePath: resolve(HERE, '../fixtures/search-to-plan.example.json'),
    title: 'SearchToPlanInput',
  },
  {
    name: 'plan-to-verification',
    schemaPath: resolve(HERE, '../schemas/plan-to-verification.schema.json'),
    fixturePath: resolve(HERE, '../fixtures/plan-to-verification.example.json'),
    title: 'PlanToVerificationInput',
  },
];

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function deepEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function resolveRef(ref, root) {
  if (!ref.startsWith('#/')) throw new Error(`외부 $ref는 지원하지 않습니다: ${ref}`);
  return ref
    .slice(2)
    .split('/')
    .map((part) => part.replaceAll('~1', '/').replaceAll('~0', '~'))
    .reduce((value, key) => value?.[key], root);
}

function matchesType(value, expected) {
  if (expected === 'null') return value === null;
  if (expected === 'object') return isObject(value);
  if (expected === 'array') return Array.isArray(value);
  if (expected === 'integer') return Number.isInteger(value);
  if (expected === 'number') return typeof value === 'number' && Number.isFinite(value);
  if (expected === 'string') return typeof value === 'string';
  if (expected === 'boolean') return typeof value === 'boolean';
  return true;
}

function validate(value, schema, root, path = '$') {
  if (schema === true) return [];
  if (schema === false) return [`${path}: 허용되지 않는 값입니다`];
  if (!isObject(schema)) return [`${path}: 스키마 노드가 객체가 아닙니다`];

  if (schema.$ref) {
    const target = resolveRef(schema.$ref, root);
    if (!target) return [`${path}: $ref 대상을 찾을 수 없습니다 (${schema.$ref})`];
    return validate(value, target, root, path);
  }

  if (schema.oneOf) {
    const results = schema.oneOf.map((candidate) => validate(value, candidate, root, path));
    const matches = results.filter((errors) => errors.length === 0).length;
    if (matches !== 1) return [`${path}: oneOf 중 정확히 하나와 일치해야 합니다 (일치 ${matches}개)`];
  }

  if ('const' in schema && !deepEqual(value, schema.const)) {
    return [`${path}: ${JSON.stringify(schema.const)} 값이어야 합니다`];
  }
  if (schema.enum && !schema.enum.some((candidate) => deepEqual(value, candidate))) {
    return [`${path}: 허용 값이 아닙니다 (${JSON.stringify(value)})`];
  }

  if (schema.type) {
    const allowed = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!allowed.some((expected) => matchesType(value, expected))) {
      return [`${path}: 타입이 ${allowed.join('|')}이어야 합니다`];
    }
  }

  const errors = [];
  if (isObject(value)) {
    for (const key of schema.required ?? []) {
      if (!(key in value)) errors.push(`${path}.${key}: 필수 필드가 없습니다`);
    }

    const properties = schema.properties ?? {};
    for (const [key, child] of Object.entries(value)) {
      if (key in properties) {
        errors.push(...validate(child, properties[key], root, `${path}.${key}`));
      } else if (schema.additionalProperties === false) {
        errors.push(`${path}.${key}: 허용되지 않은 필드입니다`);
      } else if (isObject(schema.additionalProperties)) {
        errors.push(...validate(child, schema.additionalProperties, root, `${path}.${key}`));
      }
    }
  }

  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(`${path}: 최소 ${schema.minItems}개가 필요합니다`);
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(`${path}: 최대 ${schema.maxItems}개만 허용합니다`);
    }
    if (schema.uniqueItems && new Set(value.map((item) => JSON.stringify(item))).size !== value.length) {
      errors.push(`${path}: 중복 항목이 있습니다`);
    }
    if (schema.items) {
      value.forEach((item, index) => errors.push(...validate(item, schema.items, root, `${path}[${index}]`)));
    }
  }

  if (typeof value === 'string') {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(`${path}: 최소 길이는 ${schema.minLength}입니다`);
    }
    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      errors.push(`${path}: 최대 길이는 ${schema.maxLength}입니다`);
    }
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) {
      errors.push(`${path}: 패턴 ${schema.pattern}과 일치하지 않습니다`);
    }
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push(`${path}: ${schema.minimum} 이상이어야 합니다`);
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push(`${path}: ${schema.maximum} 이하여야 합니다`);
    }
  }

  return errors;
}

function parseDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value ? null : parsed;
}

function minutes(value) {
  const [hour, minute] = value.split(':').map(Number);
  return hour * 60 + minute;
}

function checkTrip(trip, label) {
  const errors = [];
  const start = parseDate(trip.start_date);
  const end = parseDate(trip.end_date);
  if (!start) errors.push(`${label}.start_date: 실제 달력 날짜가 아닙니다`);
  if (!end) errors.push(`${label}.end_date: 실제 달력 날짜가 아닙니다`);
  if (start && end && start > end) errors.push(`${label}: start_date가 end_date보다 늦습니다`);
  if (minutes(trip.day_start_time) >= minutes(trip.day_end_time)) {
    errors.push(`${label}: day_start_time은 day_end_time보다 빨라야 합니다`);
  }
  return errors;
}

function checkSearchFixture(fixture) {
  const errors = checkTrip(fixture.trip_info, 'search.trip_info');
  const placeIds = fixture.selected.places.map((place) => place.id);
  if (new Set(placeIds).size !== placeIds.length) errors.push('search.selected.places: id가 중복됩니다');

  const selectedNames = new Set(fixture.selected.places.map((place) => place.name));
  for (const required of fixture.trip_info.persona.must_visit) {
    if (!selectedNames.has(required)) errors.push(`search.selected.places: 필수 장소 '${required}'가 선택되지 않았습니다`);
  }

  const currency = fixture.trip_info.budget_currency;
  const flightCurrency = fixture.selected.flight?.total_price.currency;
  if (flightCurrency && flightCurrency !== currency) errors.push('search.selected.flight: 예산 통화와 다릅니다');
  return errors;
}

function checkPlanFixture(fixture) {
  const errors = checkTrip(fixture.trip_info, 'verification.trip_info');
  const start = parseDate(fixture.trip_info.start_date);
  const end = parseDate(fixture.trip_info.end_date);
  if (!start || !end) return errors;

  const expectedDays = Math.round((end - start) / 86_400_000) + 1;
  if (fixture.plan.days.length !== expectedDays) {
    errors.push(`verification.plan.days: 여행 기간 ${expectedDays}일과 일수 ${fixture.plan.days.length}가 다릅니다`);
  }

  const itemIds = new Set();
  fixture.plan.days.forEach((day, dayIndex) => {
    const expectedDate = new Date(start.valueOf() + dayIndex * 86_400_000).toISOString().slice(0, 10);
    if (day.day !== dayIndex + 1) errors.push(`verification.plan.days[${dayIndex}].day: ${dayIndex + 1}이어야 합니다`);
    if (day.date !== expectedDate) errors.push(`verification.plan.days[${dayIndex}].date: ${expectedDate}이어야 합니다`);

    day.items.forEach((item, itemIndex) => {
      const at = `verification.plan.days[${dayIndex}].items[${itemIndex}]`;
      if (itemIds.has(item.id)) errors.push(`${at}.id: plan 전체에서 중복됩니다`);
      itemIds.add(item.id);
      if (itemIndex === 0 && item.travel_from_prev !== null) errors.push(`${at}.travel_from_prev: 첫 항목은 null이어야 합니다`);
      if (itemIndex > 0 && item.travel_from_prev === null) errors.push(`${at}.travel_from_prev: 이전 항목 이동 정보가 필요합니다`);
      if (minutes(item.end_time) - minutes(item.start_time) !== item.expected_duration_min) {
        errors.push(`${at}: start/end와 expected_duration_min이 일치하지 않습니다`);
      }
      if (itemIndex > 0 && item.travel_from_prev) {
        const previous = day.items[itemIndex - 1];
        const earliest = minutes(previous.end_time) + item.travel_from_prev.estimated_min;
        if (minutes(item.start_time) < earliest) errors.push(`${at}: 이전 항목에서 이동할 시간이 부족합니다`);
      }
    });
  });
  return errors;
}

async function readJson(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

async function main() {
  const loaded = {};
  let failureCount = 0;

  console.log('Voyagent handoff 계약 검사');
  for (const contract of CONTRACTS) {
    const schema = await readJson(contract.schemaPath);
    const fixture = await readJson(contract.fixturePath);
    loaded[contract.name] = { schema, fixture };

    const schemaErrors = [];
    if (schema.title !== contract.title) schemaErrors.push(`$.title: ${contract.title}이어야 합니다`);
    if (schema.type !== 'object') schemaErrors.push('$.type: object여야 합니다');
    if (!schema.$defs || !schema.properties) schemaErrors.push('$defs와 properties가 필요합니다');

    const fixtureErrors = validate(fixture, schema, schema);
    const invariantErrors = contract.name === 'search-to-plan'
      ? checkSearchFixture(fixture)
      : checkPlanFixture(fixture);
    const errors = [...schemaErrors, ...fixtureErrors, ...invariantErrors];

    if (errors.length === 0) {
      console.log(`  PASS ${contract.name}: schema + fixture + invariants`);
    } else {
      failureCount += errors.length;
      console.log(`  FAIL ${contract.name}`);
      errors.forEach((error) => console.log(`    - ${error}`));
    }
  }

  const search = loaded['search-to-plan'];
  const verification = loaded['plan-to-verification'];
  const crossErrors = [];
  if (!deepEqual(search.schema.$defs.TripInfo, verification.schema.$defs.TripInfo)) {
    crossErrors.push('두 스키마의 $defs.TripInfo가 다릅니다');
  }
  if (!deepEqual(search.schema.$defs.Persona, verification.schema.$defs.Persona)) {
    crossErrors.push('두 스키마의 $defs.Persona가 다릅니다');
  }
  if (!deepEqual(search.fixture.trip_info, verification.fixture.trip_info)) {
    crossErrors.push('두 fixture의 trip_info가 다릅니다');
  }

  const availableNames = new Set([
    ...search.fixture.selected.places.map((place) => place.name),
    ...(search.fixture.selected.stay ? [search.fixture.selected.stay.name] : []),
  ]);
  for (const day of verification.fixture.plan.days) {
    for (const item of day.items) {
      if (!availableNames.has(item.name)) crossErrors.push(`plan item '${item.name}'이 Search→Plan 선택 결과에 없습니다`);
    }
  }

  if (crossErrors.length === 0) {
    console.log('  PASS cross-handoff: shared contract + fixture continuity');
  } else {
    failureCount += crossErrors.length;
    console.log('  FAIL cross-handoff');
    crossErrors.forEach((error) => console.log(`    - ${error}`));
  }

  if (failureCount > 0) {
    console.log(`계약 위반: ${failureCount}건`);
    process.exit(1);
  }
  console.log('계약 통과: canonical handoff 2개');
}

main().catch((error) => {
  console.error(`계약 검사 실패: ${error.stack ?? error.message}`);
  process.exit(1);
});
