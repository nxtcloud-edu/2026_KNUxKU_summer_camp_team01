import { strFromU8, unzipSync } from 'fflate';

import type { ImportedPlace, PlaceCategory } from '@/lib/types';

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_IMPORT_PLACES = 200;
const DEFAULT_DURATION = 90;

export type PlaceImportDraft = {
  name: string;
  description?: string;
  area?: string;
  layer?: string;
  latitude?: number;
  longitude?: number;
  sourceUrl?: string;
  googlePlaceId?: string;
  category?: PlaceCategory;
  duration?: number;
};

export class PlaceImportError extends Error {
  constructor(message: string, readonly code: 'invalid' | 'short-link' | 'my-maps-link' | 'empty' | 'unsupported' = 'invalid') {
    super(message);
    this.name = 'PlaceImportError';
  }
}

const cleanText = (value: unknown, fallback = '') => String(value ?? fallback).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
const isFiniteCoordinate = (value: number | undefined, min: number, max: number) => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
const optionalNumber = (value: unknown) => cleanText(value) ? Number(value) : undefined;

const hashText = (value: string) => {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
};

const categoryFromText = (value?: string): PlaceCategory => {
  const normalized = value?.toLowerCase() ?? '';
  if (/food|restaurant|cafe|맛집|음식|카페/.test(normalized)) return '맛집';
  if (/museum|gallery|art|미술|박물관/.test(normalized)) return '미술관';
  if (/park|nature|garden|자연|공원|정원/.test(normalized)) return '자연';
  if (/history|temple|shrine|역사|사찰|신사/.test(normalized)) return '역사';
  if (/shop|market|shopping|쇼핑|시장/.test(normalized)) return '쇼핑';
  return '명소';
};

const deduplicateDrafts = (drafts: PlaceImportDraft[]) => {
  const seen = new Set<string>();
  return drafts.filter((draft) => {
    const key = `${draft.name.toLocaleLowerCase()}|${draft.latitude?.toFixed(6) ?? ''}|${draft.longitude?.toFixed(6) ?? ''}|${draft.sourceUrl ?? ''}`;
    if (!draft.name || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, MAX_IMPORT_PLACES);
};

export const finalizeImportedPlaces = (
  drafts: PlaceImportDraft[],
  sourceType: ImportedPlace['sourceType'],
  sourceLabel: string,
): ImportedPlace[] => {
  const normalized = deduplicateDrafts(drafts).map((draft) => ({
    ...draft,
    name: cleanText(draft.name).slice(0, 160),
    description: cleanText(draft.description).slice(0, 1000) || undefined,
    area: cleanText(draft.area || draft.layer || '가져온 장소').slice(0, 160),
    layer: cleanText(draft.layer).slice(0, 120) || undefined,
    latitude: isFiniteCoordinate(draft.latitude, -90, 90) ? draft.latitude : undefined,
    longitude: isFiniteCoordinate(draft.longitude, -180, 180) ? draft.longitude : undefined,
  }));
  const located = normalized.filter((draft) => draft.latitude !== undefined && draft.longitude !== undefined);
  const latitudes = located.map((draft) => draft.latitude!);
  const longitudes = located.map((draft) => draft.longitude!);
  const minLat = Math.min(...latitudes);
  const maxLat = Math.max(...latitudes);
  const minLng = Math.min(...longitudes);
  const maxLng = Math.max(...longitudes);

  return normalized.map((draft) => {
    const identity = `${draft.sourceUrl ?? sourceLabel}|${draft.name}|${draft.latitude ?? ''}|${draft.longitude ?? ''}`;
    let x: number | undefined;
    let y: number | undefined;
    if (draft.latitude !== undefined && draft.longitude !== undefined) {
      x = maxLng === minLng ? 50 : 14 + ((draft.longitude - minLng) / (maxLng - minLng)) * 72;
      y = maxLat === minLat ? 50 : 86 - ((draft.latitude - minLat) / (maxLat - minLat)) * 72;
    }
    return {
      id: `imported-${hashText(identity)}`,
      name: draft.name,
      category: draft.category ?? categoryFromText(`${draft.layer ?? ''} ${draft.description ?? ''}`),
      area: draft.area ?? '가져온 장소',
      duration: draft.duration ?? DEFAULT_DURATION,
      description: draft.description,
      summary: draft.description || `${sourceLabel}에서 가져온 장소`,
      layer: draft.layer,
      latitude: draft.latitude,
      longitude: draft.longitude,
      x,
      y,
      sourceType,
      sourceLabel,
      sourceUrl: draft.sourceUrl,
      googlePlaceId: draft.googlePlaceId,
    };
  });
};

const decodeUrlPart = (value: string) => {
  try {
    return decodeURIComponent(value.replace(/\+/g, ' '));
  } catch {
    return value.replace(/\+/g, ' ');
  }
};

const coordinatePair = (value: string) => {
  const match = value.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (!match) return null;
  const latitude = Number(match[1]);
  const longitude = Number(match[2]);
  return isFiniteCoordinate(latitude, -90, 90) && isFiniteCoordinate(longitude, -180, 180) ? { latitude, longitude } : null;
};

const isGoogleMapsHost = (hostname: string) =>
  hostname === 'google.com' || hostname.endsWith('.google.com') || /^(?:[a-z0-9-]+\.)*google\.(?:[a-z]{2,3}|co\.[a-z]{2})$/.test(hostname);

export const parseGoogleMapsUrl = (input: string): ImportedPlace[] => {
  let url: URL;
  try {
    url = new URL(input.trim());
  } catch {
    throw new PlaceImportError('올바른 Google Maps URL을 입력해 주세요.');
  }
  if (url.protocol !== 'https:') throw new PlaceImportError('HTTPS Google Maps 링크만 사용할 수 있어요.');
  const hostname = url.hostname.toLowerCase();
  if (hostname === 'maps.app.goo.gl' || hostname === 'goo.gl') {
    throw new PlaceImportError('단축 링크는 브라우저에서 내용을 읽을 수 없어요. 링크를 연 뒤 주소창의 전체 URL을 붙여 넣거나 장소 정보를 직접 입력해 주세요.', 'short-link');
  }
  if (!isGoogleMapsHost(hostname)) throw new PlaceImportError('Google Maps 도메인의 링크만 사용할 수 있어요.');
  if (url.pathname.includes('/maps/d/')) {
    throw new PlaceImportError('Google My Maps 공유 링크는 KML/KMZ로 내보낸 뒤 파일로 가져와 주세요.', 'my-maps-link');
  }

  const drafts: PlaceImportDraft[] = [];
  const addName = (raw: string | null, placeId?: string | null) => {
    if (!raw) return;
    const decoded = cleanText(decodeUrlPart(raw));
    const coordinates = coordinatePair(decoded);
    if (coordinates) {
      drafts.push({ name: `위치 ${coordinates.latitude.toFixed(5)}, ${coordinates.longitude.toFixed(5)}`, ...coordinates, sourceUrl: url.href, googlePlaceId: placeId ?? undefined });
      return;
    }
    if (decoded && !drafts.some((draft) => draft.name === decoded)) drafts.push({ name: decoded, sourceUrl: url.href, googlePlaceId: placeId ?? undefined });
  };

  const segments = url.pathname.split('/').filter(Boolean);
  const placeIndex = segments.indexOf('place');
  if (placeIndex >= 0) addName(segments[placeIndex + 1], url.searchParams.get('query_place_id'));
  const dirIndex = segments.indexOf('dir');
  if (dirIndex >= 0) {
    const endpoints = segments.slice(dirIndex + 1);
    const metadataIndex = endpoints.findIndex((segment) => segment.startsWith('@') || segment.startsWith('data='));
    (metadataIndex >= 0 ? endpoints.slice(0, metadataIndex) : endpoints).filter((segment) => segment && segment !== 'maps').forEach((segment) => addName(segment));
  }
  ['query', 'q', 'origin', 'destination'].forEach((key) => addName(url.searchParams.get(key), url.searchParams.get(`${key}_place_id`)));
  url.searchParams.get('waypoints')?.split('|').forEach((waypoint) => addName(waypoint));

  const atCoordinates = url.pathname.match(/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/);
  const dataCoordinates = url.pathname.match(/!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/);
  const latitude = Number(dataCoordinates?.[1] ?? atCoordinates?.[1]);
  const longitude = Number(dataCoordinates?.[2] ?? atCoordinates?.[2]);
  if (drafts.length === 1 && isFiniteCoordinate(latitude, -90, 90) && isFiniteCoordinate(longitude, -180, 180)) {
    drafts[0].latitude = latitude;
    drafts[0].longitude = longitude;
  }

  if (drafts.length === 0) throw new PlaceImportError('이 URL에서 장소명을 찾지 못했어요. /place/ 또는 query가 포함된 전체 URL을 사용해 주세요.', 'empty');
  return finalizeImportedPlaces(drafts, 'google-maps-url', 'Google Maps URL');
};

const childText = (element: Element, tagName: string) => {
  const child = Array.from(element.children).find((item) => item.localName.toLowerCase() === tagName.toLowerCase());
  return child?.textContent?.trim() ?? '';
};

const parseKml = (text: string, sourceLabel: string) => {
  const document = new DOMParser().parseFromString(text, 'application/xml');
  if (document.querySelector('parsererror')) throw new PlaceImportError('KML 파일을 읽을 수 없어요. 파일 형식을 확인해 주세요.');
  const placemarks = Array.from(document.getElementsByTagNameNS('*', 'Placemark'));
  const drafts = placemarks.map((placemark, index): PlaceImportDraft | null => {
    const point = placemark.getElementsByTagNameNS('*', 'Point')[0];
    if (!point) return null;
    const coordinatesText = point.getElementsByTagNameNS('*', 'coordinates')[0]?.textContent?.trim().split(/\s+/)[0];
    const coordinateValues = coordinatesText?.split(',').map(Number);
    const longitude = coordinateValues?.[0];
    const latitude = coordinateValues?.[1];
    let parent: Element | null = placemark.parentElement;
    let layer = '';
    while (parent && !layer) {
      if (parent.localName === 'Folder' || parent.localName === 'Document') layer = childText(parent, 'name');
      parent = parent.parentElement;
    }
    const name = childText(placemark, 'name') || `가져온 장소 ${index + 1}`;
    const description = childText(placemark, 'description');
    const address = childText(placemark, 'address');
    return {
      name,
      description,
      area: address || layer || 'My Maps',
      layer,
      latitude: isFiniteCoordinate(latitude, -90, 90) ? latitude : undefined,
      longitude: isFiniteCoordinate(longitude, -180, 180) ? longitude : undefined,
    };
  }).filter((draft): draft is PlaceImportDraft => Boolean(draft));
  if (drafts.length === 0) throw new PlaceImportError('KML에서 장소 마커를 찾지 못했어요.', 'empty');
  return finalizeImportedPlaces(drafts, 'my-maps-file', sourceLabel);
};

const parseCsvRows = (text: string) => {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = '';
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"') {
      if (quoted && text[index + 1] === '"') { value += '"'; index += 1; } else quoted = !quoted;
    } else if (character === ',' && !quoted) {
      row.push(value.trim()); value = '';
    } else if ((character === '\n' || character === '\r') && !quoted) {
      if (character === '\r' && text[index + 1] === '\n') index += 1;
      row.push(value.trim());
      if (row.some(Boolean)) rows.push(row);
      row = []; value = '';
    } else value += character;
  }
  row.push(value.trim());
  if (row.some(Boolean)) rows.push(row);
  return rows;
};

const normalizedHeader = (value: string) => value.toLowerCase().replace(/[\s_-]/g, '');
const findColumn = (headers: string[], aliases: string[]) => headers.findIndex((header) => aliases.includes(header));

const parseCsv = (text: string, sourceLabel: string) => {
  const rows = parseCsvRows(text.replace(/^\uFEFF/, ''));
  if (rows.length < 2) throw new PlaceImportError('CSV에 헤더와 장소 데이터가 필요해요.', 'empty');
  const headers = rows[0].map(normalizedHeader);
  const nameIndex = findColumn(headers, ['name', 'title', 'place', 'placename', '이름', '장소', '장소명']);
  const latIndex = findColumn(headers, ['lat', 'latitude', '위도']);
  const lngIndex = findColumn(headers, ['lng', 'lon', 'long', 'longitude', '경도']);
  const addressIndex = findColumn(headers, ['address', '주소', 'area', '지역']);
  const descriptionIndex = findColumn(headers, ['description', 'desc', 'note', '설명', '메모']);
  const layerIndex = findColumn(headers, ['layer', 'group', 'folder', '레이어', '그룹']);
  const urlIndex = findColumn(headers, ['url', 'link', 'mapsurl', '링크']);
  if (nameIndex < 0 && (latIndex < 0 || lngIndex < 0)) throw new PlaceImportError('CSV에는 장소명 또는 위도·경도 컬럼이 필요해요.');
  const drafts = rows.slice(1).map((row, index): PlaceImportDraft => {
    const latitude = optionalNumber(row[latIndex]);
    const longitude = optionalNumber(row[lngIndex]);
    return {
      name: cleanText(row[nameIndex]) || `가져온 장소 ${index + 1}`,
      area: cleanText(row[addressIndex] || row[layerIndex] || '가져온 장소'),
      description: cleanText(row[descriptionIndex]),
      layer: cleanText(row[layerIndex]),
      sourceUrl: cleanText(row[urlIndex]) || undefined,
      latitude: isFiniteCoordinate(latitude, -90, 90) ? latitude : undefined,
      longitude: isFiniteCoordinate(longitude, -180, 180) ? longitude : undefined,
    };
  });
  return finalizeImportedPlaces(drafts, 'my-maps-file', sourceLabel);
};

const objectValue = (record: Record<string, unknown>, keys: string[]) => {
  const entry = Object.entries(record).find(([key]) => keys.includes(normalizedHeader(key)));
  return entry?.[1];
};

const parseJson = (text: string, sourceLabel: string) => {
  let parsed: unknown;
  try { parsed = JSON.parse(text); } catch { throw new PlaceImportError('JSON 파일을 읽을 수 없어요.'); }
  const features = typeof parsed === 'object' && parsed !== null && 'features' in parsed && Array.isArray((parsed as { features?: unknown[] }).features)
    ? (parsed as { features: unknown[] }).features
    : Array.isArray(parsed) ? parsed : [parsed];
  const drafts = features.map((entry, index): PlaceImportDraft | null => {
    if (typeof entry !== 'object' || entry === null) return null;
    const feature = entry as Record<string, unknown>;
    const properties = typeof feature.properties === 'object' && feature.properties !== null ? feature.properties as Record<string, unknown> : feature;
    const geometry = typeof feature.geometry === 'object' && feature.geometry !== null ? feature.geometry as { type?: string; coordinates?: unknown[] } : null;
    if (geometry && geometry.type !== 'Point') return null;
    const coordinates = geometry?.type === 'Point' && Array.isArray(geometry.coordinates) ? geometry.coordinates : undefined;
    const longitude = optionalNumber(coordinates?.[0] ?? objectValue(properties, ['lng', 'lon', 'longitude', '경도']));
    const latitude = optionalNumber(coordinates?.[1] ?? objectValue(properties, ['lat', 'latitude', '위도']));
    const name = cleanText(objectValue(properties, ['name', 'title', 'place', 'placename', '이름', '장소', '장소명'])) || `가져온 장소 ${index + 1}`;
    return {
      name,
      area: cleanText(objectValue(properties, ['address', 'area', '주소', '지역', 'layer', '레이어'])) || '가져온 장소',
      description: cleanText(objectValue(properties, ['description', 'desc', 'note', '설명', '메모'])),
      layer: cleanText(objectValue(properties, ['layer', 'group', 'folder', '레이어', '그룹'])),
      sourceUrl: cleanText(objectValue(properties, ['url', 'link', 'mapsurl', '링크'])) || undefined,
      latitude: isFiniteCoordinate(latitude, -90, 90) ? latitude : undefined,
      longitude: isFiniteCoordinate(longitude, -180, 180) ? longitude : undefined,
    };
  }).filter((draft): draft is PlaceImportDraft => Boolean(draft));
  if (drafts.length === 0) throw new PlaceImportError('JSON에서 장소 데이터를 찾지 못했어요.', 'empty');
  return finalizeImportedPlaces(drafts, 'my-maps-file', sourceLabel);
};

export const parsePlaceFile = async (file: File): Promise<ImportedPlace[]> => {
  if (file.size > MAX_FILE_BYTES) throw new PlaceImportError('파일은 10MB 이하만 가져올 수 있어요.');
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (extension === 'kmz') {
    const entries = unzipSync(new Uint8Array(await file.arrayBuffer()));
    const kmlName = Object.keys(entries).find((name) => name.toLowerCase().endsWith('.kml'));
    if (!kmlName) throw new PlaceImportError('KMZ 안에서 KML 문서를 찾지 못했어요.');
    return parseKml(strFromU8(entries[kmlName]), file.name);
  }
  const text = await file.text();
  if (extension === 'kml') return parseKml(text, file.name);
  if (extension === 'csv') return parseCsv(text, file.name);
  if (extension === 'json' || extension === 'geojson') return parseJson(text, file.name);
  throw new PlaceImportError('KML, KMZ, CSV, JSON, GeoJSON 파일만 지원해요.', 'unsupported');
};

export const createManualUrlPlace = (input: {
  url: string;
  name: string;
  latitude?: number;
  longitude?: number;
  area?: string;
}): ImportedPlace => finalizeImportedPlaces([{
  name: input.name,
  area: input.area || 'Google Maps 공유 장소',
  latitude: input.latitude,
  longitude: input.longitude,
  sourceUrl: input.url,
}], 'google-maps-url', 'Google Maps 공유 링크')[0];
