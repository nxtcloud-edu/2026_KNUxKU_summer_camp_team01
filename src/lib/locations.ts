import { CITIES, ORIGIN_CITIES } from '@/lib/data';
import type { City, Trip } from '@/lib/types';

export type LocationSearchResponse = {
  locations: City[];
  source: 'google-places';
};

export const catalogLocation = (city: City): City => ({ ...city, source: 'catalog' });

export const getTripOrigin = (trip: Trip): City | undefined =>
  trip.originLocation ?? ORIGIN_CITIES.find((city) => city.id === trip.originId);

export const getTripDestination = (trip: Trip): City | undefined =>
  trip.destinationLocation ?? CITIES.find((city) => city.id === trip.destinationId);

export const locationSubtitle = (location: City) => {
  const details = [location.country, ...location.airportCodes].filter(Boolean);
  return details.join(' · ') || location.nameEn;
};
