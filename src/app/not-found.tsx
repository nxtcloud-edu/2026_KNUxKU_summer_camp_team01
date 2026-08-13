import Link from 'next/link';
import { MapPinOff } from 'lucide-react';

export default function NotFound() {
  return <main className="system-state"><MapPinOff size={34} /><h1>페이지를 찾을 수 없어요</h1><p>주소를 확인하거나 홈에서 새 여행을 시작해 주세요.</p><Link href="/" className="button button--primary">홈으로</Link></main>;
}
