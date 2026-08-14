import type { ImportedPlace, Trip, TripPlace } from '@/lib/types';

export const getTripPlace = (trip: Pick<Trip, 'importedPlaces' | 'searchPlaceOffers'>, id: string): TripPlace | undefined =>
  trip.importedPlaces?.[id] ?? trip.searchPlaceOffers?.find((place) => place.id === id);

export const getTripPlaces = (trip: Pick<Trip, 'importedPlaces' | 'searchPlaceOffers'>): TripPlace[] => {
  const imported = Object.values(trip.importedPlaces ?? {});
  const searched = trip.searchPlaceOffers ?? [];
  const importedIds = new Set(imported.map((place) => place.id));
  return [...searched.filter((place) => !importedIds.has(place.id)), ...imported];
};

export const isImportedPlace = (place: TripPlace): place is ImportedPlace =>
  place.sourceType === 'google-maps-url' || place.sourceType === 'my-maps-file';

export type MappableTripPlace = TripPlace & { x: number; y: number };

export const getMappablePlaces = (places: TripPlace[]): MappableTripPlace[] => places.filter((place): place is MappableTripPlace =>
  Number.isFinite(place.x) && Number.isFinite(place.y));
