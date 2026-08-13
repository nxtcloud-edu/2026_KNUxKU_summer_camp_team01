'use client';

import Link from 'next/link';
import { CircleAlert } from 'lucide-react';

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="system-state"><CircleAlert size={34} /><h1>화면을 불러오지 못했어요</h1><p>잠시 후 다시 시도해 주세요.</p><div><button className="button button--primary" onClick={reset}>다시 시도</button><Link href="/" className="button button--secondary">홈으로</Link></div></main>;
}
