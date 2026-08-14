import { describe, expect, it } from 'vitest';

import { getTripPlaces } from '@/lib/places';
import { getTripFlights, getTripStays } from '@/lib/searchResults';
import { createTrip, type FlightOffer, type Place, type StayOffer } from '@/lib/types';

describe('agent search result selectors', () => {
  it('does not silently substitute static catalog data', () => {
    const trip = createTrip('empty-search');

    expect(getTripFlights(trip)).toEqual([]);
    expect(getTripStays(trip)).toEqual([]);
    expect(getTripPlaces(trip)).toEqual([]);
  });

  it('returns only agent and explicitly imported results', () => {
    const trip = createTrip('live-search');
    const flight = { id: 'live-flight' } as FlightOffer;
    const stay = { id: 'live-stay' } as StayOffer;
    const place = { id: 'live-place' } as Place;
    trip.searchFlightOffers = [flight];
    trip.searchStayOffers = [stay];
    trip.searchPlaceOffers = [place];
    trip.importedPlaces = {
      imported: {
        id: 'imported',
        name: 'Imported place',
        category: '명소',
        area: 'Tokyo',
        duration: 60,
        sourceType: 'google-maps-url',
        sourceLabel: 'Google Maps',
      },
    };

    expect(getTripFlights(trip)).toEqual([flight]);
    expect(getTripStays(trip)).toEqual([stay]);
    expect(getTripPlaces(trip).map(({ id }) => id)).toEqual(['live-place', 'imported']);
  });
});
