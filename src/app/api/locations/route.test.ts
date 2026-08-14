import { afterEach, describe, expect, it, vi } from 'vitest';

import { GET } from '@/app/api/locations/route';

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.GOOGLE_MAPS_API_KEY;
});

describe('GET /api/locations', () => {
  it('maps Google Places city predictions without exposing the API key', async () => {
    process.env.GOOGLE_MAPS_API_KEY = 'test-key';
    const googleFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      suggestions: [{
        placePrediction: {
          placeId: 'tokyo-place-id',
          structuredFormat: {
            mainText: { text: '도쿄' },
            secondaryText: { text: '일본' },
          },
        },
      }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', googleFetch);

    const response = await GET(new Request('http://localhost/api/locations?query=도쿄'));
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.locations[0]).toMatchObject({
      id: 'tokyo-place-id',
      placeId: 'tokyo-place-id',
      name: '도쿄',
      country: '일본',
      source: 'google-places',
    });
    expect(googleFetch).toHaveBeenCalledWith(
      'https://places.googleapis.com/v1/places:autocomplete',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Goog-Api-Key': 'test-key' }),
      }),
    );
    expect(JSON.stringify(payload)).not.toContain('test-key');
  });

  it('returns a service error when the server key is missing', async () => {
    const response = await GET(new Request('http://localhost/api/locations?query=도쿄'));
    expect(response.status).toBe(503);
  });
});
