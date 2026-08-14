import { describe, expect, it } from 'vitest';

import { resolvePrimaryAirport } from '@/lib/airports';

describe('primary airport resolver', () => {
  it('prefers a valid IATA code supplied with the selected city', () => {
    expect(resolvePrimaryAirport({ name: 'Custom', nameEn: 'Custom', airportCodes: [' hnd ', 'NRT'] })).toBe('HND');
  });

  it('accepts airport codes that exist in the bundled factual dataset', () => {
    expect(resolvePrimaryAirport({ name: '서울', nameEn: 'Seoul', airportCodes: ['ICN'] })).toBe('ICN');
    expect(resolvePrimaryAirport({ name: 'Tokyo', nameEn: 'Tokyo', airportCodes: ['NRT'] })).toBe('NRT');
  });

  it('does not invent an airport for an unsupported city', () => {
    expect(resolvePrimaryAirport({ name: 'Unknown City', nameEn: 'Unknown City', airportCodes: [] })).toBeUndefined();
  });
});
