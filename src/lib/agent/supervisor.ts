import { VERIFICATION_CHECKS } from '@/lib/data';
import { resolvePrimaryAirport } from '@/lib/airports';
import { getTripDestination, getTripOrigin } from '@/lib/locations';
import { getTripPlace, getTripPlaces } from '@/lib/places';
import { getTripFlight, getTripStay } from '@/lib/searchResults';
import type { FlightOffer, ItineraryDay, ItineraryItem, Place, StayOffer, Trip, TripPlace, VerificationCheck } from '@/lib/types';

type WalkingLevel = '낮음' | '중' | '중간' | '높음';
type SupervisorCategory = '관광지' | '식사' | '카페' | '쇼핑' | '휴식' | '숙소';

type SupervisorTripInfo = {
  destination: string;
  start_date: string;
  end_date: string;
  num_travelers: number;
  budget_total: number;
  budget_currency: 'KRW';
  budget_includes: SupervisorCategory[];
  transport_mode: string;
  day_start_time: string;
  day_end_time: string;
  persona: {
    description: string;
    must_visit: string[];
    avoid: string[];
    pace: '여유' | '보통' | '빡빡';
    max_walking_level: WalkingLevel;
  };
};

type SupervisorPlanItem = {
  id: string;
  name: string;
  category: SupervisorCategory;
  start_time: string;
  end_time: string;
  lat: number;
  lng: number;
  price: number;
  price_unit: 'per_person' | 'per_stay';
  opening_hours: string;
  closed_days: string[];
  expected_duration_min: number;
  physical_intensity: WalkingLevel;
  note: string;
  travel_from_prev: null | { mode: string; estimated_min: number; distance_km: number };
};

type SupervisorSelectedPlace = Omit<SupervisorPlanItem, 'start_time' | 'end_time' | 'travel_from_prev'>;

export type SupervisorInput = {
  schema_version: '1.0';
  trip_info: SupervisorTripInfo;
  selected: {
    flight: null | {
      id: string;
      outbound: { depart_at: string; arrive_at: string; duration_min: number };
      inbound: null | { depart_at: string; arrive_at: string; duration_min: number };
      total_price: { amount: number; currency: 'KRW' };
    };
    stay: null | {
      id: string;
      name: string;
      lat: number;
      lng: number;
      price: number;
      price_unit: 'per_stay';
      check_in_time: string;
      check_out_time: string;
      note: string;
    };
    places: SupervisorSelectedPlace[];
  };
};

export type VerificationInput = {
  schema_version: '1.0';
  trip_info: SupervisorTripInfo;
  plan: { days: Array<{ day: number; date: string; items: SupervisorPlanItem[] }> };
};

export type AgentPlanResult = {
  itinerary: ItineraryDay[];
  verification: VerificationCheck[] | null;
};

export type AgentSearchResult = {
  flights: FlightOffer[];
  stays: StayOffer[];
  places: Place[];
  providers: Record<string, string>;
};

export class SupervisorContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SupervisorContractError';
  }
}

const COORDINATES: Record<string, { lat: number; lng: number }> = {
  sensoji: { lat: 35.7148, lng: 139.7967 },
  skytree: { lat: 35.7101, lng: 139.8107 },
  museum: { lat: 35.7188, lng: 139.7765 },
  meiji: { lat: 35.6764, lng: 139.6993 },
  shibuya: { lat: 35.658, lng: 139.7016 },
  shinjuku: { lat: 35.6852, lng: 139.71 },
  teamlab: { lat: 35.6491, lng: 139.7898 },
  tsukiji: { lat: 35.6654, lng: 139.7707 },
  ginza: { lat: 35.6697, lng: 139.7649 },
  gracery: { lat: 35.6955, lng: 139.7009 },
  granbell: { lat: 35.6972, lng: 139.7072 },
  sequence: { lat: 35.691, lng: 139.702 },
};

const AIRPORT_COORDINATES: Record<string, { lat: number; lng: number }> = {
  ICN: { lat: 37.4602, lng: 126.4407 },
  GMP: { lat: 37.5583, lng: 126.7906 },
  NRT: { lat: 35.772, lng: 140.3929 },
  HND: { lat: 35.5494, lng: 139.7798 },
};

const CATEGORY_MAP: Record<TripPlace['category'], SupervisorCategory> = {
  명소: '관광지',
  역사: '관광지',
  자연: '휴식',
  미술관: '관광지',
  맛집: '식사',
  쇼핑: '쇼핑',
};

const VERIFICATION_LABELS: Record<string, string> = {
  physical_feasibility: '물리적 이동 가능성',
  budget: '예산',
  operating_hours: '영업시간 · 휴관일',
  daily_schedule: '하루 일정량',
  must_visit: '필수 방문지',
  avoid: '회피 조건',
  pace: '여행 페이스',
  walking_level: '도보 강도',
  duration_realism: '체류시간 현실성',
  time_realism: '시간 현실성',
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const assertDate = (value: string, label: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new SupervisorContractError(`${label} 날짜가 필요합니다.`);
  return value;
};


const parsePrice = (value?: string) => {
  if (!value || value.includes('무료')) return 0;
  return Number(value.replace(/[^0-9.]/g, '')) || 0;
};

const closedDays = (place: TripPlace) => {
  const closed = place.closed ?? '';
  return [
    ['월', '월요일'], ['화', '화요일'], ['수', '수요일'], ['목', '목요일'],
    ['금', '금요일'], ['토', '토요일'], ['일', '일요일'],
  ].flatMap(([short, full]) => closed.includes(full) || closed.includes(`${short} 휴관`) ? [full] : []);
};

const canonicalOpeningHours = (place: TripPlace) => {
  const candidate = place.openingHours?.find((value) => /^\s*\d{2}:\d{2}\s*[-~–]\s*\d{2}:\d{2}\s*$/.test(value));
  return candidate?.trim().replace(/[~–]/, '-') ?? '09:00-18:00';
};

const placeCoordinates = (place: TripPlace) => {
  const lat = place.latitude ?? COORDINATES[place.id]?.lat;
  const lng = place.longitude ?? COORDINATES[place.id]?.lng;
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    throw new SupervisorContractError(`${place.name}의 위도·경도가 없어 Supervisor에 전달할 수 없습니다.`);
  }
  return { lat: lat as number, lng: lng as number };
};

const airportCoordinates = (title: string) => {
  const code = title.match(/\b[A-Z]{3}\b/)?.[0];
  return code ? AIRPORT_COORDINATES[code] : undefined;
};

const toSelectedPlace = (trip: Trip, place: TripPlace): SupervisorSelectedPlace => {
  const { lat, lng } = placeCoordinates(place);
  return {
    id: place.id,
    name: place.name,
    category: CATEGORY_MAP[place.category],
    lat,
    lng,
    price: parsePrice(place.price),
    price_unit: 'per_person',
    opening_hours: canonicalOpeningHours(place),
    closed_days: closedDays(place),
    expected_duration_min: trip.placeDurations[place.id] ?? place.duration,
    physical_intensity: place.category === '자연' ? '중간' : '낮음',
    note: place.note ?? '',
  };
};

const minutesBetween = (start: string, end: string) => {
  const [startHour, startMinute] = start.split(':').map(Number);
  const [endHour, endMinute] = end.split(':').map(Number);
  const difference = endHour * 60 + endMinute - (startHour * 60 + startMinute);
  return difference >= 0 ? difference : difference + 24 * 60;
};

const parseFlightLeg = (value: string, date: string) => {
  const match = value.match(/(\d{2}:\d{2})\s+\S+\s+→\s+(\d{2}:\d{2})\s+\S+/);
  if (!match) throw new SupervisorContractError(`항공편 시간 형식을 해석할 수 없습니다: ${value}`);
  return {
    depart_at: `${date}T${match[1]}`,
    arrive_at: `${date}T${match[2]}`,
    duration_min: minutesBetween(match[1], match[2]),
  };
};

const getTripInfo = (trip: Trip): SupervisorTripInfo => {
  const destination = getTripDestination(trip);
  const interests = trip.persona.interests.join(', ');
  const description = trip.persona.companionDescription.trim()
    || `${trip.persona.companion ?? '여행자'}와 함께하는 ${interests || '관광'} 중심 여행`;
  return {
    destination: destination?.name ?? trip.destinationId ?? '도쿄',
    start_date: assertDate(trip.startDate, '출발'),
    end_date: assertDate(trip.endDate, '귀국'),
    num_travelers: Math.max(1, trip.persona.adults),
    budget_total: 1_600_000,
    budget_currency: 'KRW',
    budget_includes: ['숙소', '식사', '관광지', '쇼핑'],
    transport_mode: trip.persona.preferredTransportModes.includes('walking') ? '도보·대중교통' : '대중교통',
    day_start_time: '09:00',
    day_end_time: '22:00',
    persona: {
      description,
      // Selecting candidates means "available for planning". It is not the same as
      // the canonical must-visit constraint, which the current UI does not collect.
      must_visit: [],
      avoid: trip.persona.pace === 'relaxed' ? ['장시간 도보', '복잡한 환승'] : [],
      pace: trip.persona.pace === 'relaxed' ? '여유' : trip.persona.pace === 'packed' ? '빡빡' : '보통',
      max_walking_level: trip.persona.pace === 'packed' ? '높음' : trip.persona.pace === 'relaxed' ? '낮음' : '중간',
    },
  };
};

export const toSupervisorInput = (trip: Trip): SupervisorInput => {
  const places = getTripPlaces(trip)
    .filter((place) => trip.selectedPlaceIds.includes(place.id))
    .map((place) => toSelectedPlace(trip, place));
  if (places.length === 0) throw new SupervisorContractError('Supervisor 일정 생성에는 선택 장소가 한 곳 이상 필요합니다.');

  const flight = getTripFlight(trip, trip.selectedFlightId);
  const stay = getTripStay(trip, trip.selectedStayId);
  const stayCoordinates = stay ? (Number.isFinite(stay.latitude) && Number.isFinite(stay.longitude)
    ? { lat: stay.latitude as number, lng: stay.longitude as number }
    : COORDINATES[stay.id]) : undefined;
  if (stay && !stayCoordinates) throw new SupervisorContractError(`${stay.name}의 좌표가 없습니다.`);

  return {
    schema_version: '1.0',
    trip_info: getTripInfo(trip),
    selected: {
      flight: flight ? {
        id: flight.id,
        outbound: parseFlightLeg(flight.outbound, trip.startDate),
        inbound: parseFlightLeg(flight.inbound, trip.endDate),
        total_price: { amount: flight.price * Math.max(1, trip.persona.adults), currency: 'KRW' },
      } : null,
      stay: stay ? {
        id: stay.id,
        name: stay.name,
        lat: stayCoordinates!.lat,
        lng: stayCoordinates!.lng,
        price: stay.total,
        price_unit: 'per_stay',
        check_in_time: '15:00',
        check_out_time: '11:00',
        note: stay.station,
      } : null,
      places,
    },
  };
};

export const toSearchInput = (trip: Trip) => {
  const origin = getTripOrigin(trip);
  const destination = getTripDestination(trip);
  const includeFlights = trip.persona.includeFlights !== false;
  const originIata = resolvePrimaryAirport(origin);
  const destinationIata = resolvePrimaryAirport(destination);
  if (includeFlights && (!originIata || !destinationIata)) {
    const unresolved = [!originIata ? origin?.name ?? trip.originId ?? '출발지' : '', !destinationIata ? destination?.name ?? trip.destinationId ?? '목적지' : '']
      .filter(Boolean)
      .join(', ');
    throw new SupervisorContractError(`${unresolved}의 공항 코드를 확인할 수 없습니다. 현재 지원되는 도시를 선택해 주세요.`);
  }
  return {
    trip_info: getTripInfo(trip),
    origin: origin?.name ?? trip.originId ?? '',
    origin_iata: originIata,
    destination_iata: destinationIata,
    include_flights: includeFlights,
    flight_trip_type: 'round_trip',
    include_stays: trip.persona.includeStays !== false,
    max_results: 10,
  };
};

const recordArray = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.filter(isRecord) : [];
const text = (value: unknown, fallback = '') => typeof value === 'string' ? value : fallback;
const number = (value: unknown, fallback = 0) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
const hhmm = (value: unknown) => text(value).match(/T(\d{2}:\d{2})/)?.[1] ?? '00:00';
const durationLabel = (minutes: number) => `${Math.floor(minutes / 60)}시간 ${minutes % 60}분`;

export const fromSearchPayload = (trip: Trip, payload: unknown): AgentSearchResult => {
  const outer = isRecord(payload) ? payload : {};
  const result = isRecord(outer.result) ? outer.result : {};
  const origin = getTripOrigin(trip);
  const destination = getTripDestination(trip);
  const originCode = origin?.airportCodes[0] ?? '출발지';
  const destinationCode = destination?.airportCodes[0] ?? '목적지';
  const flightsResult = isRecord(result.flights) ? result.flights : {};
  const staysResult = isRecord(result.stays) ? result.stays : {};
  const placesResult = isRecord(result.places) ? result.places : {};

  const flights = recordArray(flightsResult.candidates).flatMap((candidate): FlightOffer[] => {
    const offer = isRecord(candidate.offer) ? candidate.offer : {};
    const outbound = isRecord(offer.outbound) ? offer.outbound : {};
    const inbound = isRecord(offer.inbound) ? offer.inbound : null;
    const totalPrice = isRecord(offer.total_price) ? offer.total_price : {};
    const id = text(offer.id);
    if (!id) return [];
    const codes = Array.isArray(candidate.carrier_codes) ? candidate.carrier_codes.filter((value): value is string => typeof value === 'string') : [];
    const code = codes[0] ?? id;
    const duration = number(outbound.duration_min);
    return [{
      id,
      originId: trip.originId ?? originCode,
      destinationId: trip.destinationId ?? destinationCode,
      airline: code,
      code,
      price: Math.round(number(totalPrice.amount) / Math.max(1, trip.persona.adults)),
      outbound: `${hhmm(outbound.depart_at)} ${originCode} → ${hhmm(outbound.arrive_at)} ${destinationCode}`,
      inbound: inbound ? `${hhmm(inbound.depart_at)} ${destinationCode} → ${hhmm(inbound.arrive_at)} ${originCode}` : '편도',
      duration: durationLabel(duration),
      tag: 'Search Agent',
      note: 'Search Agent가 검증한 항공편 후보입니다.',
    }];
  });

  const stays = recordArray(staysResult.candidates).flatMap((candidate, index): StayOffer[] => {
    const stay = isRecord(candidate.stay) ? candidate.stay : {};
    const id = text(stay.id);
    if (!id) return [];
    const price = Math.round(number(stay.price));
    const rawRating = number(candidate.rating, 4);
    return [{
      id,
      type: 'hotel',
      features: ['central', 'station'],
      name: text(stay.name, '숙소'),
      area: destination?.name ?? '목적지',
      address: text(stay.note, destination?.name ?? ''),
      description: text(stay.note, 'Search Agent가 검증한 숙소 후보입니다.'),
      rating: rawRating <= 5 ? rawRating * 2 : rawRating,
      reviews: 0,
      price,
      total: price,
      station: text(stay.note, '교통 정보를 확인해 주세요.'),
      tag: 'Search Agent',
      image: `https://picsum.photos/seed/${encodeURIComponent(id)}/800/520`,
      x: 30 + (index % 3) * 25,
      y: 35 + (index % 2) * 25,
      latitude: number(stay.lat),
      longitude: number(stay.lng),
    }];
  });

  const categoryMap: Record<string, Place['category']> = { 관광지: '명소', 식사: '맛집', 카페: '맛집', 쇼핑: '쇼핑', 휴식: '자연', 숙소: '명소' };
  const places = recordArray(placesResult.candidates).flatMap((candidate, index): Place[] => {
    const place = isRecord(candidate.place) ? candidate.place : {};
    const id = text(place.id);
    if (!id) return [];
    const duration = number(place.expected_duration_min, 90);
    return [{
      id,
      name: text(place.name, '장소'),
      category: categoryMap[text(place.category)] ?? '명소',
      area: destination?.name ?? '목적지',
      duration,
      rating: number(candidate.rating, 0),
      reviews: 0,
      price: number(place.price) ? `${number(place.price).toLocaleString()}원` : '무료',
      summary: text(place.note, 'Search Agent가 검증한 장소입니다.'),
      note: text(place.note, 'Search Agent 추천'),
      image: `https://picsum.photos/seed/${encodeURIComponent(id)}/640/420`,
      x: 20 + (index % 4) * 20,
      y: 25 + (index % 3) * 25,
      latitude: number(place.lat),
      longitude: number(place.lng),
      openingHours: [text(place.opening_hours, '운영시간 확인 필요')],
      closed: Array.isArray(place.closed_days) ? place.closed_days.join(', ') : undefined,
    }];
  });

  const providers = isRecord(outer.providers)
    ? Object.fromEntries(Object.entries(outer.providers).filter((entry): entry is [string, string] => typeof entry[1] === 'string'))
    : {};
  return { flights, stays, places, providers };
};

const toPlanItem = (trip: Trip, item: ItineraryItem, previousItem: ItineraryItem | undefined, dayIndex: number, itemIndex: number): SupervisorPlanItem => {
  const place = item.placeId ? getTripPlace(trip, item.placeId) : getTripPlaces(trip).find((candidate) => candidate.name === item.title);
  const stay = item.kind === 'stay' ? getTripStay(trip, trip.selectedStayId) : undefined;
  const coordinate = place ? placeCoordinates(place) : stay
    ? (Number.isFinite(stay.latitude) && Number.isFinite(stay.longitude) ? { lat: stay.latitude as number, lng: stay.longitude as number } : COORDINATES[stay.id])
    : item.kind === 'flight' ? airportCoordinates(item.title) : undefined;
  if (!coordinate) throw new SupervisorContractError(`${item.title}의 좌표가 없어 일정을 검증할 수 없습니다.`);
  const category: SupervisorCategory = item.kind === 'stay' ? '숙소' : item.kind === 'meal' ? '식사' : place ? CATEGORY_MAP[place.category] : '관광지';
  const endMinutes = item.time.split(':').map(Number);
  const endTotal = endMinutes[0] * 60 + endMinutes[1] + item.duration;
  return {
    id: `d${dayIndex + 1}-${itemIndex + 1}`,
    name: item.title,
    category,
    start_time: item.time,
    end_time: `${String(Math.floor(endTotal / 60) % 24).padStart(2, '0')}:${String(endTotal % 60).padStart(2, '0')}`,
    lat: coordinate.lat,
    lng: coordinate.lng,
    price: stay?.price ?? parsePrice(place?.price),
    price_unit: item.kind === 'stay' ? 'per_stay' : 'per_person',
    opening_hours: item.kind === 'stay' ? '체크인 15:00 이후' : place?.openingHours?.join(', ') || '09:00-18:00',
    closed_days: place ? closedDays(place) : [],
    expected_duration_min: item.duration,
    physical_intensity: place?.category === '자연' ? '중간' : '낮음',
    note: stay?.station ?? place?.note ?? '',
    travel_from_prev: itemIndex === 0 ? null : {
      mode: previousItem?.travelMode || '대중교통',
      estimated_min: previousItem?.travelMinutes ?? 0,
      distance_km: Math.round(((previousItem?.travelMinutes ?? 0) * 0.35) * 100) / 100,
    },
  };
};

export const toVerificationInput = (trip: Trip): VerificationInput => {
  if (!trip.itinerary?.length) throw new SupervisorContractError('검증할 일정이 없습니다.');
  return {
    schema_version: '1.0',
    trip_info: getTripInfo(trip),
    plan: {
      days: trip.itinerary.map((day, dayIndex) => ({
        day: dayIndex + 1,
        date: day.date,
        items: day.items.map((item, itemIndex) => toPlanItem(trip, item, day.items[itemIndex - 1], dayIndex, itemIndex)),
      })),
    },
  };
};

const verificationChecks = (value: unknown): VerificationCheck[] | null => {
  if (!isRecord(value) || !isRecord(value.checks)) return null;
  return Object.entries(value.checks).map(([key, raw], index) => {
    const check = isRecord(raw) ? raw : {};
    const rawStatus = typeof check.status === 'string' ? check.status : 'pass';
    const status: VerificationCheck['status'] = rawStatus === 'fail' ? 'conflict'
      : rawStatus === 'warning' ? 'warning'
        : rawStatus === 'skipped' ? 'skipped' : 'pass';
    const issues = Array.isArray(check.issues) ? check.issues : [];
    const firstIssue = issues.find(isRecord);
    const message = firstIssue && typeof firstIssue.message === 'string'
      ? firstIssue.message
      : status === 'pass' ? `${VERIFICATION_LABELS[key] ?? key} 조건을 충족해요.` : `${VERIFICATION_LABELS[key] ?? key} 확인이 필요해요.`;
    return { id: `V${index + 1}`, label: VERIFICATION_LABELS[key] ?? key, status, message };
  });
};

export const fromVerificationPayload = (payload: unknown): VerificationCheck[] =>
  verificationChecks(payload) ?? VERIFICATION_CHECKS.map((check) => ({ ...check, status: 'skipped', message: '검증 결과 형식을 확인할 수 없어요.' }));

export const fromSupervisorPayload = (trip: Trip, payload: unknown): AgentPlanResult => {
  if (!isRecord(payload) || !isRecord(payload.plan) || !isRecord(payload.plan.plan) || !Array.isArray(payload.plan.plan.days)) {
    throw new SupervisorContractError('Supervisor 완료 응답에 plan.days가 없습니다.');
  }
  const tripPlaces = getTripPlaces(trip);
  const itinerary: ItineraryDay[] = payload.plan.plan.days.map((rawDay, dayIndex) => {
    if (!isRecord(rawDay) || !Array.isArray(rawDay.items) || typeof rawDay.date !== 'string') {
      throw new SupervisorContractError('Supervisor 일정의 day 형식이 올바르지 않습니다.');
    }
    const rawItems = rawDay.items.filter(isRecord);
    const items: ItineraryItem[] = rawItems.map((rawItem, itemIndex) => {
      const title = typeof rawItem.name === 'string' ? rawItem.name : `일정 ${itemIndex + 1}`;
      const category = typeof rawItem.category === 'string' ? rawItem.category : '관광지';
      const place = tripPlaces.find((candidate) => candidate.name === title);
      const nextTravel = itemIndex + 1 < rawItems.length && isRecord(rawItems[itemIndex + 1].travel_from_prev)
        ? rawItems[itemIndex + 1].travel_from_prev as Record<string, unknown> : undefined;
      const kind: ItineraryItem['kind'] = category === '숙소' ? 'stay' : category === '식사' || category === '카페' ? 'meal' : 'place';
      return {
        id: typeof rawItem.id === 'string' ? rawItem.id : `d${dayIndex + 1}-${itemIndex + 1}`,
        ...(place ? { placeId: place.id } : {}),
        kind,
        time: typeof rawItem.start_time === 'string' ? rawItem.start_time : '09:00',
        title,
        duration: typeof rawItem.expected_duration_min === 'number' ? rawItem.expected_duration_min : 60,
        travelMinutes: typeof nextTravel?.estimated_min === 'number' ? nextTravel.estimated_min : 0,
        travelMode: typeof nextTravel?.mode === 'string' ? nextTravel.mode : undefined,
      };
    });
    return { id: `day-${dayIndex + 1}`, date: rawDay.date, title: `Day ${dayIndex + 1}`, items };
  });
  return { itinerary, verification: verificationChecks(payload.verification) };
};
