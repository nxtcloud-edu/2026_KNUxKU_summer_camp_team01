import { describe, expect, it } from 'vitest';

import {
  fromSupervisorPayload,
  SupervisorContractError,
  toSearchInput,
  toSupervisorInput,
  toVerificationInput,
} from '@/lib/agent/supervisor';
import { FLIGHTS, PLACES, STAYS } from '@/lib/data';
import { createTrip } from '@/lib/types';

const createSelectedTrip = () => {
  const trip = createTrip('supervisor-trip');
  trip.destinationId = 'tokyo';
  trip.startDate = '2026-08-17';
  trip.endDate = '2026-08-20';
  trip.searchFlightOffers = FLIGHTS.filter((offer) => offer.id === 'ke703');
  trip.searchStayOffers = STAYS.filter((stay) => stay.id === 'gracery');
  trip.searchPlaceOffers = PLACES.filter((place) => ['sensoji', 'skytree'].includes(place.id));
  trip.selectedFlightId = 'ke703';
  trip.selectedStayId = 'gracery';
  trip.selectedPlaceIds = ['sensoji'];
  trip.placeDurations.sensoji = 120;
  trip.persona.companion = '친구';
  trip.persona.adults = 2;
  trip.persona.pace = 'balanced';
  trip.persona.interests = ['역사·문화'];
  return trip;
};

describe('Supervisor contract adapter', () => {
  it('validates selected IATA codes against the bundled airport dataset', () => {
    const trip = createTrip('airport-resolution');
    trip.startDate = '2026-08-17';
    trip.endDate = '2026-08-20';
    trip.originId = 'google-seoul';
    trip.destinationId = 'google-tokyo';
    trip.originLocation = { id: 'google-seoul', name: '서울', nameEn: '서울', country: '대한민국', flag: '🇰🇷', currency: '', timezone: '', image: '', color: '', airportCodes: ['ICN'], source: 'google-places' };
    trip.destinationLocation = { id: 'google-tokyo', name: '도쿄', nameEn: '도쿄', country: '일본', flag: '🇯🇵', currency: '', timezone: '', image: '', color: '', airportCodes: ['NRT'], source: 'google-places' };

    expect(toSearchInput(trip)).toMatchObject({ origin_iata: 'ICN', destination_iata: 'NRT', include_flights: true });
  });

  it('fails closed when a flight-search city has no verified IATA mapping', () => {
    const trip = createTrip('unsupported-airport');
    trip.startDate = '2026-08-17';
    trip.endDate = '2026-08-20';
    trip.originLocation = { id: 'unknown', name: 'Unknown City', nameEn: 'Unknown City', country: '', flag: '', currency: '', timezone: '', image: '', color: '', airportCodes: [], source: 'google-places' };
    trip.originId = 'unknown';
    trip.destinationId = 'tokyo';

    expect(() => toSearchInput(trip)).toThrow(SupervisorContractError);
  });

  it('builds the integrated SearchToPlanInput without extra place fields', () => {
    const input = toSupervisorInput(createSelectedTrip());

    expect(input.schema_version).toBe('1.0');
    expect(input.trip_info).toMatchObject({
      destination: '도쿄',
      start_date: '2026-08-17',
      end_date: '2026-08-20',
      num_travelers: 2,
      budget_currency: 'KRW',
    });
    expect(input.selected.flight).toMatchObject({
      id: 'ke703',
      outbound: { depart_at: '2026-08-17T09:05', arrive_at: '2026-08-17T11:20', duration_min: 135 },
      total_price: { amount: 1_368_000, currency: 'KRW' },
    });
    expect(input.selected.stay).toMatchObject({ id: 'gracery', price_unit: 'per_stay' });
    expect(input.selected.places[0]).toMatchObject({
      id: 'sensoji',
      name: '센소지',
      category: '관광지',
      expected_duration_min: 120,
      lat: 35.7148,
      lng: 139.7967,
    });
    expect(Object.keys(input.selected.places[0]).sort()).toEqual([
      'category', 'closed_days', 'expected_duration_min', 'id', 'lat', 'lng', 'name',
      'note', 'opening_hours', 'physical_intensity', 'price', 'price_unit',
    ]);
  });

  it('converts a Supervisor done payload to frontend itinerary and verification state', () => {
    const trip = createSelectedTrip();
    const result = fromSupervisorPayload(trip, {
      plan: {
        schema_version: '1.0',
        trip_info: toSupervisorInput(trip).trip_info,
        plan: {
          days: [{
            day: 1,
            date: '2026-08-17',
            items: [{
              id: 'd1-1', name: '센소지', category: '관광지', start_time: '09:00', end_time: '11:00',
              lat: 35.7148, lng: 139.7967, price: 0, price_unit: 'per_person', opening_hours: '06:00-17:00',
              closed_days: [], expected_duration_min: 120, physical_intensity: '중간', note: '', travel_from_prev: null,
            }, {
              id: 'd1-2', name: '도쿄 스카이트리', category: '관광지', start_time: '11:15', end_time: '13:15',
              lat: 35.7101, lng: 139.8107, price: 2100, price_unit: 'per_person', opening_hours: '10:00-21:00',
              closed_days: [], expected_duration_min: 120, physical_intensity: '낮음', note: '',
              travel_from_prev: { mode: '대중교통', estimated_min: 15, distance_km: 1.78 },
            }],
          }],
        },
      },
      verification: {
        possible: true,
        checks: {
          operating_hours: { status: 'warning', issues: [{ message: '운영시간을 다시 확인해 주세요.' }] },
          budget: { status: 'pass', issues: [] },
        },
      },
    });

    expect(result.itinerary[0].items[0]).toMatchObject({
      id: 'd1-1', placeId: 'sensoji', kind: 'place', time: '09:00', title: '센소지', duration: 120,
      travelMinutes: 15, travelMode: '대중교통',
    });
    expect(result.verification).toEqual([
      expect.objectContaining({ label: '영업시간 · 휴관일', status: 'warning', message: '운영시간을 다시 확인해 주세요.' }),
      expect.objectContaining({ label: '예산', status: 'pass' }),
    ]);

    trip.itinerary = result.itinerary;
    const verificationInput = toVerificationInput(trip);
    expect(verificationInput.plan.days[0].items[0]).toMatchObject({
      id: 'd1-1', name: '센소지', start_time: '09:00', end_time: '11:00', travel_from_prev: null,
    });
    expect(verificationInput.plan.days[0].items[1].travel_from_prev).toMatchObject({
      mode: '대중교통', estimated_min: 15,
    });
  });

  it('maps an airport arrival item to its coordinates when verifying an itinerary', () => {
    const trip = createSelectedTrip();
    trip.itinerary = [{
      id: 'day-1',
      date: '2026-08-17',
      title: '도착',
      items: [{
        id: 'arrival', kind: 'flight', time: '11:20', title: 'NRT 공항 도착', duration: 80,
        travelMinutes: 78, travelMode: '대중교통',
      }],
    }];

    const input = toVerificationInput(trip);

    expect(input.plan.days[0].items[0]).toMatchObject({
      name: 'NRT 공항 도착',
      lat: 35.772,
      lng: 140.3929,
    });
  });
});
