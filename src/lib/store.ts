'use client';

import { create, type StateCreator } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { FLIGHTS, PLACES, VERIFICATION_CHECKS } from '@/lib/data';
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
  generateItinerary: (id: string) => void;
  verifyItinerary: (id: string) => void;
  removeTrip: (id: string) => void;
};

const addDays = (iso: string, amount: number) => {
  const base = iso ? new Date(`${iso}T12:00:00`) : new Date();
  base.setDate(base.getDate() + amount);
  return base.toISOString().slice(0, 10);
};

const buildItinerary = (trip: Trip): ItineraryDay[] => {
  const selected = trip.selectedPlaceIds
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
    return { trips: { ...state.trips, [id]: { ...current, selectedPlaceIds, itinerary: null, verification: null, updatedAt: new Date().toISOString() } } };
  }),
  generateItinerary: (id) => set((state) => {
    const current = state.trips[id] ?? createTrip(id);
    return { trips: { ...state.trips, [id]: { ...current, itinerary: buildItinerary(current), verification: null, updatedAt: new Date().toISOString() } } };
  }),
  verifyItinerary: (id) => set((state) => {
    const current = state.trips[id] ?? createTrip(id);
    return { trips: { ...state.trips, [id]: { ...current, verification: VERIFICATION_CHECKS, updatedAt: new Date().toISOString() } } };
  }),
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
  await persistApi?.rehydrate();
};
