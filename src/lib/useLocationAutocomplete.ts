'use client';

import { useEffect, useState } from 'react';

import type { LocationSearchResponse } from '@/lib/locations';
import type { City } from '@/lib/types';

type LocationAutocompleteState = {
  query: string;
  locations: City[];
  loading: boolean;
  error: string | null;
  fromGoogle: boolean;
};

export function useLocationAutocomplete(query: string, defaults: City[]): LocationAutocompleteState {
  const normalized = query.trim();
  const [state, setState] = useState<LocationAutocompleteState>({
    query: '',
    locations: [],
    loading: false,
    error: null,
    fromGoogle: false,
  });

  useEffect(() => {
    if (normalized.length < 2) return;

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/locations?query=${encodeURIComponent(normalized)}`, {
          cache: 'no-store',
          signal: controller.signal,
        });
        const payload = await response.json() as LocationSearchResponse & { detail?: string };
        if (!response.ok) throw new Error(payload.detail ?? '도시 검색에 실패했습니다.');
        setState({ query: normalized, locations: payload.locations, loading: false, error: null, fromGoogle: true });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          query: normalized,
          locations: [],
          loading: false,
          error: error instanceof Error ? error.message : '도시 검색에 실패했습니다.',
          fromGoogle: false,
        });
      }
    }, 300);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [defaults, normalized]);

  if (normalized.length < 2) return { query: normalized, locations: defaults, loading: false, error: null, fromGoogle: false };
  if (state.query !== normalized) return { query: normalized, locations: [], loading: true, error: null, fromGoogle: false };
  return state;
}
