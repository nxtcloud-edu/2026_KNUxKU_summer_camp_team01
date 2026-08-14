import { FLIGHTS, PLACES, STAYS, VERIFICATION_CHECKS } from '@/lib/data';
import type { AgentTaskId, AgentTaskInput } from '@/lib/agent/contracts';
import { getTripPlaces } from '@/lib/places';
import type { ItineraryDay, ItineraryItem, Trip, VerificationCheck } from '@/lib/types';

export class AgentInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AgentInputError';
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const requireRecord = (value: unknown, field = '요청 본문') => {
  if (!isRecord(value)) throw new AgentInputError(`${field}은 JSON 객체여야 합니다.`);
  return value;
};

const optionalString = (record: Record<string, unknown>, field: string) => {
  const value = record[field];
  if (value !== undefined && value !== null && typeof value !== 'string') {
    throw new AgentInputError(`${field}은 문자열 또는 null이어야 합니다.`);
  }
};

export function validateTaskInput(task: AgentTaskId, input: unknown): void {
  const body = requireRecord(input);
  if (task === 'itineraryGenerate') {
    const trip = requireRecord(body.trip, 'trip');
    if (typeof trip.id !== 'string' || trip.id.length === 0) {
      throw new AgentInputError('trip.id가 필요합니다.');
    }
    if (!Array.isArray(trip.selectedPlaceIds)) {
      throw new AgentInputError('trip.selectedPlaceIds는 배열이어야 합니다.');
    }
    return;
  }
  if (task === 'itineraryVerify') {
    const trip = requireRecord(body.trip, 'trip');
    if (!Array.isArray(trip.itinerary)) {
      throw new AgentInputError('trip.itinerary는 배열이어야 합니다.');
    }
    return;
  }
  optionalString(body, 'destinationId');
  if (task === 'flightSearch') optionalString(body, 'originId');
}

const addDays = (iso: string, amount: number) => {
  const base = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00Z`) : new Date();
  base.setUTCDate(base.getUTCDate() + amount);
  return base.toISOString().slice(0, 10);
};

export function buildItinerary(trip: Trip): ItineraryDay[] {
  const availablePlaces = getTripPlaces(trip);
  const selected = [...new Set(trip.selectedPlaceIds)]
    .map((id) => availablePlaces.find((place) => place.id === id))
    .filter((place): place is (typeof availablePlaces)[number] => Boolean(place));
  const places = selected.length > 0 ? selected : availablePlaces.slice(0, 5);
  const rawDays = trip.startDate && trip.endDate
    ? Math.round((new Date(trip.endDate).getTime() - new Date(trip.startDate).getTime()) / 86_400_000) + 1
    : 3;
  const dayCount = Math.max(1, Math.min(14, Number.isFinite(rawDays) ? rawDays : 3));
  const days: ItineraryDay[] = Array.from({ length: dayCount }, (_, index) => ({
    id: `day-${index + 1}`,
    date: addDays(trip.startDate, index),
    title: ['도착 · 아사쿠사', '시부야 · 하라주쿠', '우에노 · 도요스', '긴자 · 도심 산책'][index] ?? '도쿄 탐험',
    items: [],
  }));
  const flight = FLIGHTS.find((offer) => offer.id === trip.selectedFlightId);
  if (flight) {
    const arrival = flight.outbound.split(' → ')[1]?.split(' ') ?? [];
    days[0].items.push({
      id: 'arrival', kind: 'flight', time: arrival[0] ?? '11:20',
      title: `${arrival[1] ?? '목적지'} 공항 도착`, duration: 80,
      travelMinutes: 78, travelMode: '대중교통',
    });
  }
  if (trip.selectedStayId) {
    days[0].items.push({
      id: 'checkin', kind: 'stay', time: '14:00', title: '호텔 체크인',
      duration: 30, travelMinutes: 8, travelMode: '도보',
    });
  }
  places.forEach((place, index) => {
    const day = days[index % dayCount];
    const position = day.items.filter((item) => item.kind === 'place').length;
    const hour = Math.min(20, 10 + position * 3 + (index % dayCount === 0 ? 4 : 0));
    day.items.push({
      id: `item-${place.id}`,
      placeId: place.id,
      kind: 'place',
      time: `${String(hour).padStart(2, '0')}:00`,
      title: place.name,
      duration: place.duration,
      travelMinutes: 8 + ((index * 7) % 23),
      travelMode: index % 2 === 0 ? '도보' : '대중교통',
    });
  });
  return days;
}

const isMonday = (date: string) => /^\d{4}-\d{2}-\d{2}$/.test(date) && new Date(`${date}T12:00:00Z`).getUTCDay() === 1;
const findPlace = (item: ItineraryItem) => PLACES.find((place) => place.id === item.placeId);

export function verifyItinerary(itinerary: ItineraryDay[]): VerificationCheck[] {
  const checks: VerificationCheck[] = VERIFICATION_CHECKS.map((check) => ({ ...check, status: 'pass', message: `${check.label} 조건을 충족해요.` }));
  const update = (id: string, patch: Partial<VerificationCheck>) => {
    const index = checks.findIndex((check) => check.id === id);
    if (index >= 0) checks[index] = { ...checks[index], ...patch };
  };
  if (itinerary.length === 0) {
    return checks.map((check) => ({ ...check, status: 'skipped', message: '검증할 일정이 없어요.' }));
  }
  const mondayClosures = itinerary.flatMap((day) => day.items.filter((item) => isMonday(day.date) && Boolean(findPlace(item)?.closed)));
  if (mondayClosures.length) update('V1', { status: 'conflict', message: `월요일 휴관 장소 ${mondayClosures.length}곳을 다른 날로 옮겨야 해요.` });
  const longTransfers = itinerary.flatMap((day) => day.items.filter((item) => (item.travelMinutes ?? 0) > 45));
  if (longTransfers.length) update('V2', { status: 'warning', message: `45분이 넘는 이동 ${longTransfers.length}건의 여유 시간을 확인해 주세요.` });
  const overloadedDays = itinerary.filter((day) => day.items.reduce((sum, item) => sum + item.duration + (item.travelMinutes ?? 0), 0) > 600);
  if (overloadedDays.length) update('V5', { status: 'warning', message: `활동 시간이 10시간을 넘는 날이 ${overloadedDays.length}일 있어요.` });
  const reservations = itinerary.flatMap((day) => day.items.filter((item) => Boolean(findPlace(item)?.reservation)));
  if (reservations.length) update('V9', { status: 'warning', message: `사전 예약이 필요한 장소가 ${reservations.length}곳 있어요.` });
  return checks;
}

export function resolveTask(task: 'flightSearch', input: AgentTaskInput['flightSearch']): typeof FLIGHTS;
export function resolveTask(task: 'staySearch', input: AgentTaskInput['staySearch']): typeof STAYS;
export function resolveTask(task: 'placeDiscovery', input: AgentTaskInput['placeDiscovery']): typeof PLACES;
export function resolveTask(task: 'itineraryGenerate', input: AgentTaskInput['itineraryGenerate']): ItineraryDay[];
export function resolveTask(task: 'itineraryVerify', input: AgentTaskInput['itineraryVerify']): VerificationCheck[];
export function resolveTask(task: AgentTaskId, input: AgentTaskInput[AgentTaskId]) {
  switch (task) {
    case 'flightSearch': {
      const search = input as AgentTaskInput['flightSearch'];
      const matches = FLIGHTS.filter((offer) =>
        (!search.originId || offer.originId === search.originId) &&
        (!search.destinationId || offer.destinationId === search.destinationId));
      return matches.length ? matches : FLIGHTS;
    }
    case 'staySearch': return STAYS;
    case 'placeDiscovery': return PLACES;
    case 'itineraryGenerate': return buildItinerary((input as AgentTaskInput['itineraryGenerate']).trip);
    case 'itineraryVerify': return verifyItinerary((input as AgentTaskInput['itineraryVerify']).trip.itinerary ?? []);
  }
}
