import { describe, expect, it } from 'vitest';

import { createAgentEvents } from '@/lib/agent/events';
import { AgentInputError, buildItinerary, validateTaskInput, verifyItinerary } from '@/lib/agent/service';
import { createTrip } from '@/lib/types';

describe('agent input validation', () => {
  it('rejects a missing trip for itinerary generation', () => {
    expect(() => validateTaskInput('itineraryGenerate', {})).toThrow(AgentInputError);
  });

  it('accepts the search input used by the frontend', () => {
    expect(() => validateTaskInput('flightSearch', { originId: 'seoul', destinationId: 'tokyo' })).not.toThrow();
  });
});

describe('planning service', () => {
  it('builds a bounded itinerary containing selected places', () => {
    const trip = createTrip('test-trip');
    trip.startDate = '2026-08-17';
    trip.endDate = '2026-08-20';
    trip.selectedPlaceIds = ['sensoji', 'skytree'];

    const itinerary = buildItinerary(trip);
    expect(itinerary).toHaveLength(4);
    expect(itinerary.flatMap((day) => day.items).map((item) => item.placeId).filter(Boolean)).toEqual(['sensoji', 'skytree']);
  });

  it('reports Monday closures and reservation requirements from itinerary data', () => {
    const trip = createTrip('verify-trip');
    trip.startDate = '2026-08-17';
    trip.endDate = '2026-08-17';
    trip.selectedPlaceIds = ['museum', 'skytree'];

    const checks = verifyItinerary(buildItinerary(trip));
    expect(checks.find((check) => check.id === 'V1')?.status).toBe('conflict');
    expect(checks.find((check) => check.id === 'V9')?.status).toBe('warning');
  });
});

describe('SSE event contract', () => {
  it('emits ordered events and a final payload', async () => {
    const previousDelay = process.env.AGENT_STREAM_DELAY_MS;
    process.env.AGENT_STREAM_DELAY_MS = '0';
    const events = [];
    try {
      for await (const event of createAgentEvents('flightSearch', { originId: 'seoul', destinationId: 'tokyo' }, new AbortController().signal)) {
        events.push(event);
      }
    } finally {
      if (previousDelay === undefined) delete process.env.AGENT_STREAM_DELAY_MS;
      else process.env.AGENT_STREAM_DELAY_MS = previousDelay;
    }
    expect(events.map((event) => event.seq)).toEqual(events.map((_, index) => index));
    expect(events.at(-1)?.type).toBe('done');
    expect(events.some((event) => event.type === 'tool_result')).toBe(true);
  });
});
