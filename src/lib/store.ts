'use client';

import { create, type StateCreator } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { FLIGHTS, PLACES, VERIFICATION_CHECKS } from '@/lib/data';
import { applyItineraryEdit, cloneItinerary, isVerificationCurrent, type ItineraryEdit } from '@/lib/itinerary';

import { createTrip, type ItineraryDay, type StepId, type Trip } from '@/lib/types';

type TripPatch = Partial<Omit<Trip, 'persona'>> & { persona?: Partial<Trip['persona']> };

type TripStore = {
  trips: Record<string, Trip>;
  hasHydrated: boolean;
  setHasHydrated: (value: boolean) => void;
  ensureTrip: (id: string) => void;
  updateTrip: (id: string, patch: TripPatch) => void;
  completeStep: (id: string, step: StepId, next: StepId) => void;
  togglePlace: (id: string, placeId: string) => void;
  addSelectedPlacesToItinerary: (id: string) => number;
  addPlaceToItinerary: (id: string, placeId: string) => boolean;
  removePlaceFromItinerary: (id: string, placeId: string) => boolean;
  generateItinerary: (id: string) => void;
  applyItineraryEdit: (tripId: string, edit: ItineraryEdit) => void;
  updateItineraryItemDuration: (tripId: string, dayId: string, itemId: string, duration: number) => void;
  verifyItinerary: (id: string) => void;
  saveItinerary: (id: string) => boolean;
  removeTrip: (id: string) => void;
};

const addDays = (iso: string, amount: number) => {
  const base = iso ? new Date(`${iso}T12:00:00`) : new Date();
  base.setDate(base.getDate() + amount);
  return base.toISOString().slice(0, 10);
};

const toMinutes = (time: string) => {
  const [hours, minutes] = time.split(':').map(Number);
  return hours * 60 + minutes;
};

const formatTime = (minutes: number) => {
  const normalized = ((minutes % 1440) + 1440) % 1440;
  return `${String(Math.floor(normalized / 60)).padStart(2, '0')}:${String(normalized % 60).padStart(2, '0')}`;
};

const recalculateDayTimes = (day: ItineraryDay): ItineraryDay => {
  if (day.items.length === 0) return day;

  let startMinutes = toMinutes(day.items[0].time);
  const items = day.items.map((item, index) => {
    if (index > 0) {
      const previous = day.items[index - 1];
      startMinutes += previous.duration + (previous.travelMinutes ?? 0);
    }
    return { ...item, time: formatTime(startMinutes) };
  });

  return { ...day, items };
};

const buildItinerary = (trip: Trip): ItineraryDay[] => {
  const selected = [...new Set(trip.selectedPlaceIds)]
    .map((id) => PLACES.find((place) => place.id === id))
    .filter((place): place is (typeof PLACES)[number] => Boolean(place));
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
  if (trip.selectedStayId) {
    days[0].items.push({ id: 'checkin', kind: 'stay', time: '14:00', title: '호텔 체크인', duration: 30, travelMinutes: 8, travelMode: '도보' });
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
      duration: place.duration,
      travelMinutes: 8 + ((index * 7) % 23),
      travelMode: index % 2 === 0 ? '도보' : '대중교통',
    });
  });
  return days;
};

const tripStoreCreator: StateCreator<TripStore> = (set) => ({
  trips: {},
  hasHydrated: false,
  setHasHydrated: (value) => set({ hasHydrated: value }),
  ensureTrip: (id) => set((state) => {
    const current = state.trips[id];
    if (!current) return { trips: { ...state.trips, [id]: createTrip(id) } };
    if (typeof current.originId === 'undefined') {
      return { trips: { ...state.trips, [id]: { ...current, originId: 'seoul' } } };
    }
    return state;
  }),
  updateTrip: (id, patch) => set((state) => {
    const current = state.trips[id] ?? createTrip(id);
    const next: Trip = {
      ...current,
      ...patch,
      persona: { ...current.persona, ...(patch.persona ?? {}) },
      updatedAt: new Date().toISOString(),
    };
    return { trips: { ...state.trips, [id]: next } };
  }),
  completeStep: (id, step, next) => set((state) => {
    const current = state.trips[id] ?? createTrip(id);
    const completedSteps = current.completedSteps.includes(step) ? current.completedSteps : [...current.completedSteps, step];
    return { trips: { ...state.trips, [id]: { ...current, completedSteps, currentStep: next, updatedAt: new Date().toISOString() } } };
  }),
  togglePlace: (id, placeId) => set((state) => {
    const current = state.trips[id] ?? createTrip(id);
    const selectedPlaceIds = current.selectedPlaceIds.includes(placeId)
      ? current.selectedPlaceIds.filter((value) => value !== placeId)
      : [...current.selectedPlaceIds, placeId];
    return { trips: { ...state.trips, [id]: { ...current, selectedPlaceIds, verification: null, updatedAt: new Date().toISOString() } } };
  }),
  addSelectedPlacesToItinerary: (id) => {
    let addedCount = 0;
    set((state) => {
      const current = state.trips[id] ?? createTrip(id);
      const selectedPlaceIds = [...new Set(current.selectedPlaceIds)];
      const selectedPlaces = selectedPlaceIds
        .map((placeId) => PLACES.find((place) => place.id === placeId))
        .filter((place): place is (typeof PLACES)[number] => Boolean(place));
      if (selectedPlaces.length === 0) return state;

      if (!current.itinerary || current.itinerary.length === 0) {
        const next = { ...current, selectedPlaceIds, itinerary: buildItinerary({ ...current, selectedPlaceIds }), verification: null, updatedAt: new Date().toISOString() };
        addedCount = next.itinerary.flatMap((day) => day.items).filter((item) => item.kind === 'place').length;
        return { trips: { ...state.trips, [id]: next } };
      }

      const scheduledPlaceIds = new Set(
        current.itinerary.flatMap((day) => day.items.map((item) => item.placeId).filter((placeId): placeId is string => Boolean(placeId))),
      );
      const placesToAdd = selectedPlaces.filter((place) => !scheduledPlaceIds.has(place.id));

      if (placesToAdd.length === 0) return state;

      const usedItemIds = new Set(current.itinerary.flatMap((day) => day.items.map((item) => item.id)));
      let itinerary = current.itinerary;
      placesToAdd.forEach((place) => {
        const targetDay = itinerary.reduce((leastBusy, day) => (
          day.items.filter((item) => item.kind === 'place').length < leastBusy.items.filter((item) => item.kind === 'place').length ? day : leastBusy
        ));
        const baseItemId = `item-${place.id}`;
        let itemId = baseItemId;
        let suffix = 2;
        while (usedItemIds.has(itemId)) itemId = `${baseItemId}-${suffix++}`;
        usedItemIds.add(itemId);

        itinerary = itinerary.map((day) => day.id === targetDay.id ? recalculateDayTimes({
          ...day,
          items: [...day.items, {
            id: itemId,
            placeId: place.id,
            kind: 'place',
            time: day.items.at(-1)?.time ?? '10:00',
            title: place.name,
            duration: place.duration,
            travelMinutes: 12,
            travelMode: '대중교통',
          }],
        }) : day);
      });

      addedCount = placesToAdd.length;
      return {
        trips: {
          ...state.trips,
          [id]: { ...current, selectedPlaceIds, itinerary, verification: null, updatedAt: new Date().toISOString() },
        },
      };
    });
    return addedCount;
  },
  addPlaceToItinerary: (id, placeId) => {
    let added = false;
    set((state) => {
      const current = state.trips[id] ?? createTrip(id);
      const place = PLACES.find((candidate) => candidate.id === placeId);
      if (!place) return state;

      const scheduledPlaceIds = new Set(
        current.itinerary?.flatMap((day) => day.items.filter((item) => item.kind === 'place').map((item) => item.placeId).filter((itemId): itemId is string => Boolean(itemId))) ?? [],
      );
      if (scheduledPlaceIds.has(placeId)) return state;

      if (!current.itinerary || current.itinerary.length === 0) {
        const selectedPlaceIds = [placeId];
        added = true;
        return {
          trips: {
            ...state.trips,
            [id]: { ...current, selectedPlaceIds, itinerary: buildItinerary({ ...current, selectedPlaceIds }), verification: null, updatedAt: new Date().toISOString() },
          },
        };
      }

      const targetDay = current.itinerary.reduce((leastBusy, day) => (
        day.items.filter((item) => item.kind === 'place').length < leastBusy.items.filter((item) => item.kind === 'place').length ? day : leastBusy
      ));
      const usedItemIds = new Set(current.itinerary.flatMap((day) => day.items.map((item) => item.id)));
      const baseItemId = `item-${place.id}`;
      let itemId = baseItemId;
      let suffix = 2;
      while (usedItemIds.has(itemId)) itemId = `${baseItemId}-${suffix++}`;

      const itinerary = current.itinerary.map((day) => day.id === targetDay.id ? recalculateDayTimes({
        ...day,
        items: [...day.items, {
          id: itemId,
          placeId: place.id,
          kind: 'place',
          time: day.items.at(-1)?.time ?? '10:00',
          title: place.name,
          duration: place.duration,
          travelMinutes: 12,
          travelMode: '대중교통',
        }],
      }) : day);

      added = true;
      return {
        trips: {
          ...state.trips,
          [id]: { ...current, selectedPlaceIds: [...scheduledPlaceIds, placeId], itinerary, verification: null, updatedAt: new Date().toISOString() },
        },
      };
    });
    return added;
  },
  removePlaceFromItinerary: (id, placeId) => {
    let removed = false;
    set((state) => {
      const current = state.trips[id] ?? createTrip(id);
      if (!current.itinerary) return state;

      const hasPlace = current.itinerary.some((day) => day.items.some((item) => item.kind === 'place' && item.placeId === placeId));
      if (!hasPlace) return state;

      const itinerary = current.itinerary.map((day) => {
        const items = day.items.filter((item) => item.kind !== 'place' || item.placeId !== placeId);
        return items.length === day.items.length ? day : recalculateDayTimes({ ...day, items });
      });
      removed = true;
      return {
        trips: {
          ...state.trips,
          [id]: { ...current, selectedPlaceIds: current.selectedPlaceIds.filter((itemId) => itemId !== placeId), itinerary, verification: null, updatedAt: new Date().toISOString() },
        },
      };
    });
    return removed;
  },
  generateItinerary: (id) => set((state) => {
    const current = state.trips[id] ?? createTrip(id);
    return { trips: { ...state.trips, [id]: { ...current, itinerary: buildItinerary(current), verification: null, verifiedItinerary: null, updatedAt: new Date().toISOString() } } };
  }),
  applyItineraryEdit: (tripId, edit) => set((state) => {
    const current = state.trips[tripId] ?? createTrip(tripId);
    if (!current.itinerary) return state;

    const itinerary = applyItineraryEdit(current.itinerary, edit);
    if (itinerary === current.itinerary) return state;

    return { trips: { ...state.trips, [tripId]: { ...current, itinerary, updatedAt: new Date().toISOString() } } };
  }),
  updateItineraryItemDuration: (tripId, dayId, itemId, duration) => set((state) => {
    const current = state.trips[tripId] ?? createTrip(tripId);
    if (!current.itinerary || !Number.isFinite(duration)) return state;

    const normalizedDuration = Math.max(30, Math.min(480, Math.round(duration / 30) * 30));
    const itinerary = current.itinerary.map((day) => {
      if (day.id !== dayId) return day;
      const hasTarget = day.items.some((item) => item.id === itemId && item.kind === 'place');
      if (!hasTarget) return day;
      return recalculateDayTimes({
        ...day,
        items: day.items.map((item) => item.id === itemId ? { ...item, duration: normalizedDuration } : item),
      });
    });

    return {
      trips: {
        ...state.trips,
        [tripId]: { ...current, itinerary, verification: null, updatedAt: new Date().toISOString() },
      },
    };
  }),
  verifyItinerary: (id) => set((state) => {
    const current = state.trips[id] ?? createTrip(id);
    return { trips: { ...state.trips, [id]: { ...current, verification: VERIFICATION_CHECKS, verifiedItinerary: current.itinerary ? cloneItinerary(current.itinerary) : null, updatedAt: new Date().toISOString() } } };
  }),
  saveItinerary: (id) => {
    let saved = false;
    set((state) => {
      const current = state.trips[id];
      if (!current?.itinerary || !isVerificationCurrent(current)) return state;

      const savedAt = new Date().toISOString();
      const completedSteps: StepId[] = current.completedSteps.includes('verify')
        ? current.completedSteps
        : [...current.completedSteps, 'verify'];
      saved = true;
      return {
        trips: {
          ...state.trips,
          [id]: {
            ...current,
            completedSteps,
            currentStep: 'verify',
            savedAt,
            updatedAt: savedAt,
          },
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
      storage: createJSONStorage(() => window.localStorage),
      partialize: (state) => ({ trips: state.trips }),
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
