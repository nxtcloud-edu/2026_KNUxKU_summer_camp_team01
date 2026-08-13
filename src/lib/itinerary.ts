import type { ItineraryDay, ItineraryItem, Trip } from '@/lib/types';

export type ItineraryEdit =
  | { type: 'remove'; dayId: string; itemId: string }
  | { type: 'move-to'; dayId: string; itemId: string; destinationIndex: number }
  | { type: 'set-duration'; dayId: string; itemId: string; duration: number }
  | { type: 'replace-item'; dayId: string; itemId: string; item: Partial<Pick<ItineraryItem, 'placeId' | 'title' | 'duration'>> };

const toMinutes = (time: string) => {
  const [hours, minutes] = time.split(':').map(Number);
  return Number.isFinite(hours) && Number.isFinite(minutes) ? hours * 60 + minutes : 0;
};

const formatTime = (minutes: number) => {
  const normalized = ((minutes % 1440) + 1440) % 1440;
  return `${String(Math.floor(normalized / 60)).padStart(2, '0')}:${String(normalized % 60).padStart(2, '0')}`;
};

const normalizeDuration = (duration: number) => Math.max(30, Math.min(480, Math.round(duration / 30) * 30));

/**
 * Rebuilds start times from an item's order, duration, and outbound travel.
 * This is intentionally independent from the UI so it can also be used by a
 * future replan service.
 */
export const recalculateDayTimes = (day: ItineraryDay): ItineraryDay => {
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

/** Creates a new itinerary state for a single user edit and recalculates that day's schedule. */
export const applyItineraryEdit = (itinerary: ItineraryDay[], edit: ItineraryEdit): ItineraryDay[] => {
  const dayIndex = itinerary.findIndex((day) => day.id === edit.dayId);
  if (dayIndex === -1) return itinerary;

  const currentDay = itinerary[dayIndex];
  const itemIndex = currentDay.items.findIndex((item) => item.id === edit.itemId);
  if (itemIndex === -1) return itinerary;

  let items = currentDay.items;

  if (edit.type === 'remove') {
    items = items.filter((item) => item.id !== edit.itemId);
  }

  if (edit.type === 'move-to') {
    if (edit.destinationIndex < 0 || edit.destinationIndex >= items.length || edit.destinationIndex === itemIndex) return itinerary;
    items = [...items];
    const [movedItem] = items.splice(itemIndex, 1);
    items.splice(edit.destinationIndex, 0, movedItem);
  }

  if (edit.type === 'set-duration') {
    if (!Number.isFinite(edit.duration)) return itinerary;
    items = items.map((item) => item.id === edit.itemId
      ? { ...item, duration: normalizeDuration(edit.duration) }
      : item);
  }

  if (edit.type === 'replace-item') {
    items = items.map((item) => item.id === edit.itemId
      ? {
        ...item,
        ...edit.item,
        duration: edit.item.duration === undefined ? item.duration : normalizeDuration(edit.item.duration),
      }
      : item);
  }

  const nextDay = recalculateDayTimes({ ...currentDay, items });
  return itinerary.map((day, index) => index === dayIndex ? nextDay : day);
};

export const cloneItinerary = (itinerary: ItineraryDay[]): ItineraryDay[] => itinerary.map((day) => ({
  ...day,
  items: day.items.map((item) => ({ ...item })),
}));

/**
 * Verification is an AI-produced snapshot.  It is current only when it was
 * produced for the same itinerary content the user is currently viewing.
 */
export const isVerificationCurrent = (trip: Pick<Trip, 'itinerary' | 'verification' | 'verifiedItinerary'>) => (
  Boolean(trip.verification && trip.itinerary && trip.verifiedItinerary)
  && JSON.stringify(trip.itinerary) === JSON.stringify(trip.verifiedItinerary)
);
