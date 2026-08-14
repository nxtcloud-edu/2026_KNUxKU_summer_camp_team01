'use client';

import { create, type StateCreator } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { FLIGHTS, PLACES, STAYS, VERIFICATION_CHECKS } from '@/lib/data';
import {
  applyItineraryEdit as applyEditToItinerary,
  cloneItinerary,
  isVerificationCurrent,
  recalculateDayTimes,
  type ItineraryEdit,
} from '@/lib/itinerary';
import { getTripPlace } from '@/lib/places';
import { createTrip, type ImportedPlace, type ItineraryDay, type StepId, type Trip, type VerificationCheck } from '@/lib/types';

type TripPatch = Partial<Omit<Trip, 'persona'>> & { persona?: Partial<Trip['persona']> };

type TripStore = {
  trips: Record<string, Trip>;
  hasHydrated: boolean;
  setHasHydrated: (value: boolean) => void;
  ensureTrip: (id: string) => void;
  updateTrip: (id: string, patch: TripPatch) => void;
  completeStep: (id: string, step: StepId, next: StepId) => void;
  togglePlace: (id: string, placeId: string) => void;
  importPlaces: (id: string, places: ImportedPlace[], selectedIds: string[], durations: Record<string, number>) => void;
  addSelectedPlacesToItinerary: (id: string) => number;
  addPlaceToItinerary: (id: string, placeId: string) => boolean;
  removePlaceFromItinerary: (id: string, placeId: string) => boolean;
  generateItinerary: (id: string) => void;
  applyAgentPlan: (id: string, itinerary: ItineraryDay[], verification: VerificationCheck[] | null) => void;
  applyItineraryEdit: (tripId: string, edit: ItineraryEdit) => void;
  updateItineraryItemDuration: (tripId: string, dayId: string, itemId: string, duration: number) => void;
  moveItineraryItem: (id: string, sourceDayId: string, itemId: string, targetDayId: string, targetIndex: number) => void;
  addPlacesToItinerary: (id: string, dayId: string, placeIds: string[]) => void;
  removeItineraryItem: (id: string, dayId: string, itemId: string) => void;
  verifyItinerary: (id: string) => void;
  applyAgentVerification: (id: string, verification: VerificationCheck[]) => void;
  saveItinerary: (id: string) => boolean;
  removeTrip: (id: string) => void;
};

const addDays = (iso: string, amount: number) => {
  const base = iso ? new Date(`${iso}T12:00:00`) : new Date();
  base.setDate(base.getDate() + amount);
  return base.toISOString().slice(0, 10);
};

const normalizeTrip = (trip: Trip): Trip => {
  const defaults = createTrip(trip.id);
  return {
    ...defaults,
    ...trip,
    originId: typeof trip.originId === 'undefined' ? 'seoul' : trip.originId,
    originLocation: trip.originLocation ?? null,
    destinationLocation: trip.destinationLocation ?? null,
    persona: {
      ...defaults.persona,
      ...(trip.persona ?? {}),
      preferredTransportModes: trip.persona?.preferredTransportModes ?? [],
      companionDescription: trip.persona?.companionDescription ?? '',
    },
    placeDurations: trip.placeDurations ?? {},
    importedPlaces: trip.importedPlaces ?? {},
    verifiedItinerary: trip.verifiedItinerary ?? null,
    savedAt: trip.savedAt ?? null,
  };
};

const structuralReset = (trip: Trip) => ({
  ...trip,
  verification: null,
  verifiedItinerary: null,
  savedAt: null,
});

const editedTrip = (trip: Trip, itinerary: ItineraryDay[]) => ({
  ...trip,
  itinerary,
  savedAt: null,
  updatedAt: new Date().toISOString(),
});

const preferredTravelMode = (trip: Trip, index: number): '도보' | '대중교통' => {
  const modes = trip.persona.preferredTransportModes ?? [];
  if (modes.length === 1) return modes[0] === 'publicTransit' ? '대중교통' : '도보';
  return index % 2 === 0 ? '도보' : '대중교통';
};

const createPlaceItem = (trip: Trip, placeId: string, itemId: string, index: number) => {
  const place = getTripPlace(trip, placeId);
  if (!place) return null;
  return {
    id: itemId,
    placeId,
    kind: 'place' as const,
    time: '10:00',
    title: place.name,
    duration: trip.placeDurations?.[placeId] ?? place.duration,
    travelMinutes: 12,
    travelMode: preferredTravelMode(trip, index),
  };
};

const buildItinerary = (trip: Trip): ItineraryDay[] => {
  const selected = [...new Set(trip.selectedPlaceIds)]
    .map((id) => getTripPlace(trip, id))
    .filter((place): place is NonNullable<typeof place> => Boolean(place));
  const places = selected.length > 0 ? selected : PLACES.slice(0, 5);
  const dayCount = Math.max(1, Math.min(5, trip.startDate && trip.endDate
    ? Math.round((new Date(trip.endDate).getTime() - new Date(trip.startDate).getTime()) / 86400000) + 1
    : 3));
  const days: ItineraryDay[] = Array.from({ length: dayCount }, (_, index) => ({
    id: `day-${index + 1}`,
    date: addDays(trip.startDate, index),
    title: ['도착 · 아사쿠사', '시부야 · 하라주쿠', '우에노 · 도요스', '긴자 · 도심 산책', '마지막 여유 일정'][index] ?? '도쿄 탐험',
    items: [],
  }));
  const selectedFlight = FLIGHTS.find((flight) => flight.id === trip.selectedFlightId);
  if (selectedFlight) {
    const arrival = selectedFlight.outbound.split(' → ')[1]?.split(' ') ?? [];
    days[0].items.push({ id: 'arrival', kind: 'flight', time: arrival[0] ?? '11:20', title: `${arrival[1] ?? '목적지'} 공항 도착`, duration: 80, travelMinutes: 78, travelMode: '대중교통' });
  }
  const selectedStay = STAYS.find((stay) => stay.id === trip.selectedStayId);
  if (selectedStay) {
    days[0].items.push({ id: 'checkin', kind: 'stay', time: '14:00', title: `${selectedStay.name} 체크인`, duration: 30, travelMinutes: 8, travelMode: '도보' });
  }
  places.forEach((place, index) => {
    const dayIndex = index % dayCount;
    const dayPosition = days[dayIndex].items.filter((item) => item.kind === 'place').length;
    const hour = 10 + dayPosition * 3 + (dayIndex === 0 ? 4 : 0);
    days[dayIndex].items.push({
      id: `item-${place.id}`,
      placeId: place.id,
      kind: 'place',
      time: `${String(Math.min(hour, 20)).padStart(2, '0')}:00`,
      title: place.name,
      duration: trip.placeDurations?.[place.id] ?? place.duration,
      travelMinutes: 8 + ((index * 7) % 23),
      travelMode: preferredTravelMode(trip, index),
    });
  });
  return days;
};

const uniqueItemId = (itinerary: ItineraryDay[], placeId: string) => {
  const used = new Set(itinerary.flatMap((day) => day.items.map((item) => item.id)));
  const base = `item-${placeId}`;
  let id = base;
  let suffix = 2;
  while (used.has(id)) id = `${base}-${suffix++}`;
  return id;
};

const itineraryPatchKeys = new Set<keyof Trip>([
  'originId',
  'destinationId',
  'originLocation',
  'destinationLocation',
  'startDate',
  'endDate',
  'persona',
  'selectedFlightId',
  'selectedStayId',
  'selectedPlaceIds',
  'placeDurations',
  'importedPlaces',
  'itinerary',
]);

const tripStoreCreator: StateCreator<TripStore> = (set) => ({
  trips: {},
  hasHydrated: false,
  setHasHydrated: (value) => set({ hasHydrated: value }),
  ensureTrip: (id) => set((state) => {
    const current = state.trips[id];
    const next = current ? normalizeTrip(current) : createTrip(id);
    if (current && JSON.stringify(current) === JSON.stringify(next)) return state;
    return { trips: { ...state.trips, [id]: next } };
  }),
  updateTrip: (id, patch) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    const invalidatesPlan = Object.keys(patch).some((key) => itineraryPatchKeys.has(key as keyof Trip));
    const base = invalidatesPlan ? structuralReset(current) : current;
    const next: Trip = {
      ...base,
      ...patch,
      persona: { ...base.persona, ...(patch.persona ?? {}) },
      verification: invalidatesPlan ? null : (patch.verification ?? base.verification),
      verifiedItinerary: invalidatesPlan ? null : (patch.verifiedItinerary ?? base.verifiedItinerary),
      savedAt: invalidatesPlan ? null : (patch.savedAt ?? base.savedAt),
      updatedAt: new Date().toISOString(),
    };
    return { trips: { ...state.trips, [id]: next } };
  }),
  completeStep: (id, step, next) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    const completedSteps = current.completedSteps.includes(step) ? current.completedSteps : [...current.completedSteps, step];
    return { trips: { ...state.trips, [id]: { ...current, completedSteps, currentStep: next, updatedAt: new Date().toISOString() } } };
  }),
  togglePlace: (id, placeId) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    if (!getTripPlace(current, placeId)) return state;
    const selectedPlaceIds = current.selectedPlaceIds.includes(placeId)
      ? current.selectedPlaceIds.filter((value) => value !== placeId)
      : [...current.selectedPlaceIds, placeId];
    return { trips: { ...state.trips, [id]: { ...current, selectedPlaceIds, savedAt: null, updatedAt: new Date().toISOString() } } };
  }),
  importPlaces: (id, places, selectedIds, durations) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    const importedPlaces = { ...current.importedPlaces };
    places.forEach((place) => { importedPlaces[place.id] = place; });
    const next = structuralReset({
      ...current,
      importedPlaces,
      selectedPlaceIds: [...new Set([...current.selectedPlaceIds, ...selectedIds])],
      placeDurations: { ...current.placeDurations, ...durations },
      itinerary: null,
      updatedAt: new Date().toISOString(),
    });
    return { trips: { ...state.trips, [id]: next } };
  }),
  addSelectedPlacesToItinerary: (id) => {
    let addedCount = 0;
    set((state) => {
      const current = normalizeTrip(state.trips[id] ?? createTrip(id));
      const selectedPlaceIds = [...new Set(current.selectedPlaceIds)].filter((placeId) => Boolean(getTripPlace(current, placeId)));
      if (selectedPlaceIds.length === 0) return state;
      if (!current.itinerary?.length) {
        const itinerary = buildItinerary({ ...current, selectedPlaceIds });
        addedCount = itinerary.flatMap((day) => day.items).filter((item) => item.kind === 'place').length;
        return { trips: { ...state.trips, [id]: editedTrip({ ...current, selectedPlaceIds }, itinerary) } };
      }
      const scheduled = new Set(current.itinerary.flatMap((day) => day.items.flatMap((item) => item.placeId ? [item.placeId] : [])));
      const placesToAdd = selectedPlaceIds.filter((placeId) => !scheduled.has(placeId));
      if (placesToAdd.length === 0) return state;
      let itinerary = current.itinerary;
      placesToAdd.forEach((placeId, index) => {
        const targetDay = itinerary.reduce((leastBusy, day) => (
          day.items.filter((item) => item.kind === 'place').length < leastBusy.items.filter((item) => item.kind === 'place').length ? day : leastBusy
        ));
        const item = createPlaceItem(current, placeId, uniqueItemId(itinerary, placeId), scheduled.size + index);
        if (!item) return;
        itinerary = itinerary.map((day) => day.id === targetDay.id
          ? recalculateDayTimes({ ...day, items: [...day.items, item] })
          : day);
        addedCount += 1;
      });
      return { trips: { ...state.trips, [id]: editedTrip({ ...current, selectedPlaceIds }, itinerary) } };
    });
    return addedCount;
  },
  addPlaceToItinerary: (id, placeId) => {
    let added = false;
    set((state) => {
      const current = normalizeTrip(state.trips[id] ?? createTrip(id));
      if (!getTripPlace(current, placeId)) return state;
      const scheduled = new Set(current.itinerary?.flatMap((day) => day.items.flatMap((item) => item.placeId ? [item.placeId] : [])) ?? []);
      if (scheduled.has(placeId)) return state;
      const selectedPlaceIds = [...new Set([...current.selectedPlaceIds, placeId])];
      if (!current.itinerary?.length) {
        const itinerary = buildItinerary({ ...current, selectedPlaceIds: [placeId] });
        added = true;
        return { trips: { ...state.trips, [id]: editedTrip({ ...current, selectedPlaceIds }, itinerary) } };
      }
      const targetDay = current.itinerary.reduce((leastBusy, day) => (
        day.items.filter((item) => item.kind === 'place').length < leastBusy.items.filter((item) => item.kind === 'place').length ? day : leastBusy
      ));
      const item = createPlaceItem(current, placeId, uniqueItemId(current.itinerary, placeId), scheduled.size);
      if (!item) return state;
      const itinerary = current.itinerary.map((day) => day.id === targetDay.id
        ? recalculateDayTimes({ ...day, items: [...day.items, item] })
        : day);
      added = true;
      return { trips: { ...state.trips, [id]: editedTrip({ ...current, selectedPlaceIds }, itinerary) } };
    });
    return added;
  },
  removePlaceFromItinerary: (id, placeId) => {
    let removed = false;
    set((state) => {
      const current = normalizeTrip(state.trips[id] ?? createTrip(id));
      if (!current.itinerary?.some((day) => day.items.some((item) => item.kind === 'place' && item.placeId === placeId))) return state;
      const itinerary = current.itinerary.map((day) => {
        const items = day.items.filter((item) => item.kind !== 'place' || item.placeId !== placeId);
        return items.length === day.items.length ? day : recalculateDayTimes({ ...day, items });
      });
      removed = true;
      return {
        trips: {
          ...state.trips,
          [id]: editedTrip({ ...current, selectedPlaceIds: current.selectedPlaceIds.filter((itemId) => itemId !== placeId) }, itinerary),
        },
      };
    });
    return removed;
  },
  generateItinerary: (id) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    const next = structuralReset({ ...current, itinerary: buildItinerary(current), updatedAt: new Date().toISOString() });
    return { trips: { ...state.trips, [id]: next } };
  }),
  applyAgentPlan: (id, itinerary, verification) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    const updatedAt = new Date().toISOString();
    return {
      trips: {
        ...state.trips,
        [id]: {
          ...current,
          itinerary,
          verification,
          verifiedItinerary: verification ? cloneItinerary(itinerary) : null,
          savedAt: null,
          updatedAt,
        },
      },
    };
  }),
  applyItineraryEdit: (tripId, edit) => set((state) => {
    const current = normalizeTrip(state.trips[tripId] ?? createTrip(tripId));
    if (!current.itinerary) return state;
    const itinerary = applyEditToItinerary(current.itinerary, edit);
    if (itinerary === current.itinerary) return state;
    return { trips: { ...state.trips, [tripId]: editedTrip(current, itinerary) } };
  }),
  updateItineraryItemDuration: (tripId, dayId, itemId, duration) => set((state) => {
    const current = normalizeTrip(state.trips[tripId] ?? createTrip(tripId));
    if (!current.itinerary) return state;
    const itinerary = applyEditToItinerary(current.itinerary, { type: 'set-duration', dayId, itemId, duration });
    if (itinerary === current.itinerary) return state;
    return { trips: { ...state.trips, [tripId]: editedTrip(current, itinerary) } };
  }),
  moveItineraryItem: (id, sourceDayId, itemId, targetDayId, targetIndex) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    if (!current.itinerary) return state;
    const days = cloneItinerary(current.itinerary);
    const sourceDay = days.find((day) => day.id === sourceDayId);
    const targetDay = days.find((day) => day.id === targetDayId);
    if (!sourceDay || !targetDay) return state;
    const sourceIndex = sourceDay.items.findIndex((item) => item.id === itemId);
    if (sourceIndex < 0 || sourceDay.items[sourceIndex].kind !== 'place') return state;
    const [movedItem] = sourceDay.items.splice(sourceIndex, 1);
    const adjustedIndex = sourceDayId === targetDayId && sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
    targetDay.items.splice(Math.max(0, Math.min(adjustedIndex, targetDay.items.length)), 0, movedItem);
    const affected = new Set([sourceDayId, targetDayId]);
    const itinerary = days.map((day) => affected.has(day.id) ? recalculateDayTimes(day) : day);
    return { trips: { ...state.trips, [id]: editedTrip(current, itinerary) } };
  }),
  addPlacesToItinerary: (id, dayId, placeIds) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    if (!current.itinerary?.some((day) => day.id === dayId)) return state;
    const existingPlaceIds = new Set(current.itinerary.flatMap((day) => day.items.flatMap((item) => item.placeId ? [item.placeId] : [])));
    let workingItinerary = current.itinerary;
    const additions = [...new Set(placeIds)].flatMap((placeId, index) => {
      if (existingPlaceIds.has(placeId)) return [];
      const item = createPlaceItem(current, placeId, uniqueItemId(workingItinerary, placeId), existingPlaceIds.size + index);
      if (!item) return [];
      existingPlaceIds.add(placeId);
      workingItinerary = workingItinerary.map((day) => day.id === dayId ? { ...day, items: [...day.items, item] } : day);
      return [placeId];
    });
    if (additions.length === 0) return state;
    const itinerary = workingItinerary.map((day) => day.id === dayId ? recalculateDayTimes(day) : day);
    const selectedPlaceIds = [...new Set([...current.selectedPlaceIds, ...additions])];
    return { trips: { ...state.trips, [id]: editedTrip({ ...current, selectedPlaceIds }, itinerary) } };
  }),
  removeItineraryItem: (id, dayId, itemId) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    if (!current.itinerary) return state;
    const targetItem = current.itinerary.find((day) => day.id === dayId)?.items.find((item) => item.id === itemId);
    if (!targetItem || targetItem.kind !== 'place') return state;
    const itinerary = current.itinerary.map((day) => day.id === dayId
      ? recalculateDayTimes({ ...day, items: day.items.filter((item) => item.id !== itemId) })
      : day);
    const remainingPlaceIds = new Set(itinerary.flatMap((day) => day.items.flatMap((item) => item.placeId ? [item.placeId] : [])));
    const selectedPlaceIds = current.selectedPlaceIds.filter((placeId) => remainingPlaceIds.has(placeId));
    return { trips: { ...state.trips, [id]: editedTrip({ ...current, selectedPlaceIds }, itinerary) } };
  }),
  verifyItinerary: (id) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    return {
      trips: {
        ...state.trips,
        [id]: {
          ...current,
          verification: VERIFICATION_CHECKS,
          verifiedItinerary: current.itinerary ? cloneItinerary(current.itinerary) : null,
          savedAt: null,
          updatedAt: new Date().toISOString(),
        },
      },
    };
  }),
  applyAgentVerification: (id, verification) => set((state) => {
    const current = normalizeTrip(state.trips[id] ?? createTrip(id));
    return {
      trips: {
        ...state.trips,
        [id]: {
          ...current,
          verification,
          verifiedItinerary: current.itinerary ? cloneItinerary(current.itinerary) : null,
          savedAt: null,
          updatedAt: new Date().toISOString(),
        },
      },
    };
  }),
  saveItinerary: (id) => {
    let saved = false;
    set((state) => {
      const current = state.trips[id] ? normalizeTrip(state.trips[id]) : null;
      if (!current?.itinerary || !isVerificationCurrent(current)) return state;
      const savedAt = new Date().toISOString();
      const completedSteps: StepId[] = current.completedSteps.includes('verify')
        ? current.completedSteps
        : [...current.completedSteps, 'verify'];
      saved = true;
      return {
        trips: {
          ...state.trips,
          [id]: { ...current, completedSteps, currentStep: 'verify', savedAt, updatedAt: savedAt },
        },
      };
    });
    return saved;
  },
  removeTrip: (id) => set((state) => {
    const trips = { ...state.trips };
    delete trips[id];
    return { trips };
  }),
});

export const useTripStore = typeof window === 'undefined'
  ? create<TripStore>()(tripStoreCreator)
  : create<TripStore>()(
    persist(tripStoreCreator, {
      name: 'voyagent:trips',
      version: 1,
      storage: createJSONStorage(() => window.localStorage),
      partialize: (state) => ({ trips: state.trips }),
      migrate: (persisted) => {
        const state = persisted as { trips?: Record<string, Trip> };
        return {
          trips: Object.fromEntries(Object.entries(state.trips ?? {}).map(([id, trip]) => [id, normalizeTrip({ ...trip, id } as Trip)])),
        };
      },
      onRehydrateStorage: () => (state) => state?.setHasHydrated(true),
      skipHydration: true,
    }),
  );

type HydratableStore = {
  persist?: { rehydrate: () => Promise<void> | void };
};

export const rehydrateTripStore = async () => {
  if (typeof window === 'undefined') return;
  const persistApi = (useTripStore as typeof useTripStore & HydratableStore).persist;
  try {
    await persistApi?.rehydrate();
  } finally {
    // Do not leave route screens in a permanent loading state if localStorage is unavailable or corrupt.
    useTripStore.getState().setHasHydrated(true);
  }
};
