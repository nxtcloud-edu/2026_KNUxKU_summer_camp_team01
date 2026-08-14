'use client';

import { Check, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { getAirportByCode, searchAirports } from '@/lib/airports';
import type { Airport } from '@/lib/types';

/**
 * Multi-select airport autocomplete backed by the full bundled international airport
 * dataset (src/lib/airports.json — no network request). Type-to-filter by IATA code,
 * airport name, city, or country. `priorityCodes` (e.g. a destination city's own
 * airports) are shown first when the search field is empty.
 */
export function AirportCombobox({ value, onChange, priorityCodes = [], placeholder = '공항명, 도시, 국가 또는 공항 코드로 검색' }: {
  value: string[];
  onChange: (codes: string[]) => void;
  priorityCodes?: string[];
  placeholder?: string;
}) {
  const [query, setQuery] = useState('');
  const priorityAirports = useMemo(
    () => priorityCodes.map((code) => getAirportByCode(code)).filter((airport): airport is Airport => Boolean(airport)),
    [priorityCodes],
  );
  const results = useMemo(() => (query.trim() ? searchAirports(query, 20) : []), [query]);

  const toggle = (code: string) => onChange(value.includes(code) ? value.filter((item) => item !== code) : [...value, code]);

  return (
    <div className="city-combobox airport-combobox">
      <div className="input-with-icon">
        <Search size={17} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={placeholder} aria-label={placeholder} />
      </div>
      {value.length > 0 && (
        <div className="interest-list airport-combobox__selected">
          {value.map((code) => {
            const airport = getAirportByCode(code);
            return (
              <button type="button" className="is-selected" key={code} onClick={() => toggle(code)}>
                {airport ? `${airport.flag} ${airport.city} · ${airport.code}` : code} <Check size={13} />
              </button>
            );
          })}
        </div>
      )}
      {!query && priorityAirports.length > 0 && (
        <div className="city-options">
          <span className="option-group">이 도시의 공항</span>
          {priorityAirports.map((airport) => (
            <button type="button" key={airport.code} className={value.includes(airport.code) ? 'is-active' : ''} onClick={() => toggle(airport.code)}>
              <span>{airport.flag}</span>
              <strong>{airport.name}</strong>
              <small>({airport.code}) · {airport.city}</small>
              {value.includes(airport.code) && <Check size={14} />}
            </button>
          ))}
        </div>
      )}
      {query && (
        <div className="city-options">
          <span className="option-group">{results.length > 0 ? '검색 결과' : '일치하는 공항이 없어요'}</span>
          {results.map((airport) => (
            <button type="button" key={airport.code} className={value.includes(airport.code) ? 'is-active' : ''} onClick={() => toggle(airport.code)}>
              <span>{airport.flag}</span>
              <strong>{airport.name}</strong>
              <small>({airport.code}) · {airport.city} · {airport.country}</small>
              {value.includes(airport.code) && <Check size={14} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
