import { AIRPORTS } from '@/lib/airports';
import { CITIES, ORIGIN_CITIES } from '@/lib/data';
import type { City } from '@/lib/types';

/**
 * City search backed by the full bundled international airport dataset (src/lib/airports.json
 * — no network request). The curated demo cities in `src/lib/data.ts` (with hand-picked images,
 * brand colors, currency, timezone) stay first-class citizens; every other airport in the world
 * is exposed as a lightweight, English-language "city" so autocomplete isn't limited to the
 * handful of cities that have deep demo data (flights/stays/places).
 */

const DEMO_CITIES = [...ORIGIN_CITIES, ...CITIES];
const DEMO_AIRPORT_CODES = new Set(DEMO_CITIES.flatMap((city) => city.airportCodes));

/** Strips disambiguating suffixes some source records carry, e.g. "Paris (Roissy-en-France, Val-d'Oise)" -> "Paris". */
const cleanCityName = (city: string) => city.replace(/\s*\([^)]*\)\s*$/, '').trim();

const FALLBACK_COLOR = '#5b6472';

/**
 * One lightweight `City` entry per airport not already covered by the curated demo cities.
 * These intentionally have no image/brand color/currency/timezone — just enough to display
 * and select a real-world destination anywhere in the dataset.
 */
const WORLD_CITIES: City[] = AIRPORTS.filter((airport) => !DEMO_AIRPORT_CODES.has(airport.code)).map((airport) => {
  const name = cleanCityName(airport.city) || airport.name;
  return {
    id: `airport:${airport.code}`,
    name,
    nameEn: name,
    country: airport.country,
    flag: airport.flag,
    currency: '',
    timezone: '',
    image: `https://picsum.photos/seed/voyagent-${airport.code.toLowerCase()}/1200/630`,
    color: FALLBACK_COLOR,
    airportCodes: [airport.code],
  };
});

/** All selectable cities: curated demo cities first, then every remaining airport worldwide. */
export const ALL_CITIES: City[] = [...DEMO_CITIES, ...WORLD_CITIES];

const CITIES_BY_ID = new Map(ALL_CITIES.map((city) => [city.id, city]));

export const getCityById = (id: string | null | undefined): City | undefined => (id ? CITIES_BY_ID.get(id) : undefined);

const DEMO_CITY_IDS = new Set(DEMO_CITIES.map((city) => city.id));

/** True for the small set of curated cities that also have demo flights/stays/places data. */
export const isDemoCity = (city: City): boolean => DEMO_CITY_IDS.has(city.id);

const normalize = (value: string) => value.toLocaleLowerCase().trim();

const searchIndex = ALL_CITIES.map((city, index) => ({
  city,
  demoRank: index < DEMO_CITIES.length ? 0 : 1,
  haystack: normalize(`${city.name} ${city.nameEn} ${city.country} ${city.airportCodes.join(' ')}`),
}));

/**
 * Ranked, prefix-aware city search for autocomplete UIs. Matches on city name, English name,
 * country, and airport code(s). Curated demo cities are ranked ahead of equally-scored world
 * cities so popular destinations keep surfacing first.
 */
export const searchCities = (query: string, limit = 20): City[] => {
  const trimmed = normalize(query);
  if (!trimmed) return [];
  const scored: { city: City; score: number; demoRank: number }[] = [];
  for (const { city, demoRank, haystack } of searchIndex) {
    const codeMatch = city.airportCodes.some((code) => code.toLowerCase() === trimmed);
    const codePrefixMatch = city.airportCodes.some((code) => code.toLowerCase().startsWith(trimmed));
    let score: number;
    if (codeMatch) score = 0;
    else if (codePrefixMatch) score = 1;
    else if (normalize(city.name).startsWith(trimmed) || normalize(city.nameEn).startsWith(trimmed)) score = 2;
    else if (haystack.includes(trimmed)) score = 3;
    else continue;
    scored.push({ city, score, demoRank });
  }
  scored.sort((a, b) => a.score - b.score || a.demoRank - b.demoRank || a.city.name.localeCompare(b.city.name));
  return scored.slice(0, limit).map((entry) => entry.city);
};
