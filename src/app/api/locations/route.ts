import type { City } from '@/lib/types';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type GooglePrediction = {
  placePrediction?: {
    placeId?: string;
    structuredFormat?: {
      mainText?: { text?: string };
      secondaryText?: { text?: string };
    };
  };
};

type GoogleAutocompleteResponse = { suggestions?: GooglePrediction[] };

const problem = (status: number, detail: string) => Response.json(
  { type: 'about:blank', title: 'Location search failed', status, detail },
  { status, headers: { 'Cache-Control': 'no-store', 'Content-Type': 'application/problem+json' } },
);

const countryFromSecondaryText = (value: string) => value.split(',').at(-1)?.trim() ?? '';

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.get('query')?.trim() ?? '';
  if (query.length < 2) return Response.json({ locations: [], source: 'google-places' });
  if (query.length > 100) return problem(400, '검색어는 100자 이하여야 합니다.');

  const apiKey = process.env.GOOGLE_MAPS_API_KEY ?? process.env.GOOGLE_PLACES_API_KEY;
  if (!apiKey) return problem(503, '서버에 GOOGLE_MAPS_API_KEY가 설정되지 않았습니다.');

  try {
    const response = await fetch('https://places.googleapis.com/v1/places:autocomplete', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': apiKey,
        'X-Goog-FieldMask': 'suggestions.placePrediction.placeId,suggestions.placePrediction.structuredFormat.mainText.text,suggestions.placePrediction.structuredFormat.secondaryText.text',
      },
      body: JSON.stringify({
        input: query,
        includedPrimaryTypes: ['(cities)'],
        languageCode: 'ko',
      }),
      cache: 'no-store',
    });
    if (!response.ok) {
      const failure = await response.json().catch(() => null) as { error?: { message?: string } } | null;
      return problem(502, failure?.error?.message ?? `Google Places API가 HTTP ${response.status}로 응답했습니다.`);
    }

    const payload = await response.json() as GoogleAutocompleteResponse;
    const locations = (payload.suggestions ?? []).flatMap((suggestion): City[] => {
      const prediction = suggestion.placePrediction;
      const id = prediction?.placeId;
      const name = prediction?.structuredFormat?.mainText?.text;
      const description = prediction?.structuredFormat?.secondaryText?.text ?? '';
      if (!id || !name) return [];
      return [{
        id,
        placeId: id,
        name,
        nameEn: name,
        country: countryFromSecondaryText(description),
        flag: '📍',
        currency: '',
        timezone: '',
        image: `https://picsum.photos/seed/${encodeURIComponent(id)}/1200/630`,
        color: '#6173c9',
        airportCodes: [],
        source: 'google-places',
      }];
    });
    return Response.json({ locations, source: 'google-places' }, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    return problem(502, error instanceof Error ? error.message : 'Google Places API에 연결하지 못했습니다.');
  }
}
