import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';

import { StoreHydrator } from '@/components/StoreHydrator';

import './globals.css';

export const metadata: Metadata = {
  title: { default: 'Voyagent — AI 여행 계획', template: '%s · Voyagent' },
  description: '도시와 날짜만 정하면 AI가 검증된 여행 일정을 만들어 드립니다.',
};

export const viewport: Viewport = { width: 'device-width', initialScale: 1, themeColor: '#ffffff' };

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="ko" suppressHydrationWarning><body><StoreHydrator />{children}</body></html>;
}
