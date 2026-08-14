import type { FlightOffer, StayOffer, Trip } from '@/lib/types';

export const getTripFlights = (trip: Pick<Trip, 'searchFlightOffers'>): FlightOffer[] =>
  trip.searchFlightOffers ?? [];

export const getTripStays = (trip: Pick<Trip, 'searchStayOffers'>): StayOffer[] =>
  trip.searchStayOffers ?? [];

export const getTripFlight = (trip: Pick<Trip, 'searchFlightOffers'>, id: string | null): FlightOffer | undefined =>
  getTripFlights(trip).find((offer) => offer.id === id);

export const getTripStay = (trip: Pick<Trip, 'searchStayOffers'>, id: string | null): StayOffer | undefined =>
  getTripStays(trip).find((offer) => offer.id === id);
