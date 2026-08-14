import { PLACES } from '@/lib/data';
import type { ImportedPlace, Trip, TripPlace } from '@/lib/types';

export const getTripPlace = (trip: Pick<Trip, 'importedPlaces'>, id: string): TripPlace | undefined =>
  trip.importedPlaces?.[id] ?? PLACES.find((place) => place.id === id);

export const getTripPlaces = (trip: Pick<Trip, 'importedPlaces'>): TripPlace[] => {
  const imported = Object.values(trip.importedPlaces ?? {});
  const importedIds = new Set(imported.map((place) => place.id));
  return [...PLACES.filter((place) => !importedIds.has(place.id)), ...imported];
};

export const isImportedPlace = (place: TripPlace): place is ImportedPlace =>
  place.sourceType === 'google-maps-url' || place.sourceType === 'my-maps-file';

export type MappableTripPlace = TripPlace & { latitude: number; longitude: number };

export const getMappablePlaces = (places: TripPlace[]): MappableTripPlace[] => places.filter((place): place is MappableTripPlace =>
  Number.isFinite(place.latitude) && Number.isFinite(place.longitude));
