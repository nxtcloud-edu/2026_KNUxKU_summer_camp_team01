import type { Airport, City } from '@/lib/types';

import airportsData from '@/lib/airports.json';

/**
 * Full international airport reference data, bundled at build time (no network calls).
 * Source: OurAirports (public domain) — large/medium airports plus small airports with
 * scheduled commercial service, deduplicated by IATA code. Korean country names are
 * pre-resolved at data-generation time via `Intl.DisplayNames`.
 */
export const AIRPORTS: Airport[] = airportsData as Airport[];

const AIRPORTS_BY_CODE = new Map(AIRPORTS.map((airport) => [airport.code, airport]));

export const getAirportByCode = (code: string): Airport | undefined => AIRPORTS_BY_CODE.get(code.toUpperCase());

const normalize = (value: string) => value.toLocaleLowerCase().trim();

const searchIndex = AIRPORTS.map((airport) => ({
  airport,
  haystack: normalize(`${airport.code} ${airport.name} ${airport.city} ${airport.country}`),
}));

/**
 * Ranked, prefix-aware airport search for autocomplete UIs.
 * Matches on IATA code, airport name, city, and country (case/locale-insensitive).
 * Exact code matches and prefix matches are ranked above generic substring matches.
 */
export const searchAirports = (query: string, limit = 20): Airport[] => {
  const trimmed = normalize(query);
  if (!trimmed) return [];
  const scored: { airport: Airport; score: number }[] = [];
  for (const { airport, haystack } of searchIndex) {
    const code = airport.code.toLowerCase();
    let score: number;
    if (code === trimmed) score = 0;
    else if (code.startsWith(trimmed)) score = 1;
    else if (normalize(airport.city).startsWith(trimmed) || normalize(airport.name).startsWith(trimmed)) score = 2;
    else if (haystack.includes(trimmed)) score = 3;
    else continue;
    scored.push({ airport, score });
  }
  scored.sort((a, b) => a.score - b.score || a.airport.code.localeCompare(b.airport.code));
  return scored.slice(0, limit).map((entry) => entry.airport);
};

/** Accepts only IATA codes present in the bundled factual airport dataset. */
export const resolvePrimaryAirport = (
  city: Pick<City, 'name' | 'nameEn' | 'airportCodes'> | null | undefined,
): string | undefined => {
  return city?.airportCodes
    .map((code) => code.trim().toUpperCase())
    .find((code) => Boolean(getAirportByCode(code)));
};
