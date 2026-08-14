'use client';

import { useEffect } from 'react';

import { rehydrateTripStore } from '@/lib/store';

export function StoreHydrator() {
  useEffect(() => {
    void rehydrateTripStore();
  }, []);

  return null;
}
