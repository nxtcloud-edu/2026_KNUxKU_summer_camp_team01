'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  BedDouble,
  Check,
  ClipboardCheck,
  Compass,
  MapPin,
  Moon,
  MoreHorizontal,
  Plane,
  Route,
  Share2,
  Sparkles,
  Users,
} from 'lucide-react';
import { useEffect, useMemo, type ReactNode } from 'react';

import { CITIES } from '@/lib/data';
import type { StepId, Trip } from '@/lib/types';

const STEP_META: { id: StepId; label: string; icon: typeof MapPin }[] = [
  { id: 'city', label: '도시', icon: MapPin },
  { id: 'persona', label: '여행 스타일', icon: Users },
  { id: 'flights', label: '항공권', icon: Plane },
  { id: 'stays', label: '숙소', icon: BedDouble },
  { id: 'places', label: '가고 싶은 곳', icon: Compass },
  { id: 'itinerary', label: '일정', icon: Route },
  { id: 'verify', label: '검증', icon: ClipboardCheck },
];

const formatDate = (value: string) => value ? value.slice(5).replace('-', '.') : '';

export function AppShell({ trip, step, children, footer }: {
  trip: Trip;
  step: StepId;
  children: ReactNode;
  footer: ReactNode;
}) {
  const router = useRouter();
  const city = CITIES.find((item) => item.id === trip.destinationId);
  const steps = useMemo(
    () => STEP_META.filter((item) =>
      (item.id !== 'flights' || trip.persona.includeFlights !== false) &&
      (item.id !== 'stays' || trip.persona.includeStays !== false)),
    [trip.persona.includeFlights, trip.persona.includeStays],
  );
  const activeIndex = steps.findIndex((item) => item.id === step);

  useEffect(() => {
    const isDark = window.localStorage.getItem('voyagent:theme') === 'dark';
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
  }, []);

  const toggleTheme = () => {
    const isDark = document.documentElement.dataset.theme !== 'dark';
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
    window.localStorage.setItem('voyagent:theme', isDark ? 'dark' : 'light');
  };

  const handleShare = async () => {
    const payload = window.btoa(unescape(encodeURIComponent(JSON.stringify(trip))));
    const url = `${window.location.origin}/trip/${trip.id}/share#${payload}`;
    await navigator.clipboard?.writeText(url);
    router.push(`/trip/${trip.id}/share#${payload}`);
  };

  return (
    <div className="app-shell">
      <header className="trip-header">
        <div className="trip-header__summary">
          <Link href="/" className="icon-button" aria-label="홈으로 돌아가기"><ArrowLeft size={18} /></Link>
          <button className="trip-title" onClick={() => router.push(`/plan/${trip.id}/city`)}>
            {city ? <><span aria-hidden>{city.flag}</span> {city.name}</> : '새 여행'}
          </button>
          {trip.startDate && <span className="trip-meta">· {formatDate(trip.startDate)}–{formatDate(trip.endDate)}</span>}
          <span className="trip-meta trip-meta--desktop">· 성인 {trip.persona.adults}명</span>
        </div>
        <div className="trip-actions">
          <span className="save-status"><Check size={14} /> <span>모든 변경사항 저장됨</span></span>
          {trip.itinerary && <button className="header-action" onClick={handleShare}><Share2 size={15} /> <span>공유</span></button>}
          <button className="icon-button" onClick={toggleTheme} aria-label="테마 변경">
            <Moon size={17} />
          </button>
          <button className="icon-button" aria-label="더보기"><MoreHorizontal size={18} /></button>
        </div>
      </header>

      <nav className="step-progress" aria-label="여행 계획 진행 단계">
        <div className="step-progress__desktop">
          {steps.map((item, index) => {
            const Icon = item.icon;
            const completed = trip.completedSteps.includes(item.id);
            const active = item.id === step;
            const canNavigate = completed || index <= activeIndex;
            return (
              <div className="step-wrap" key={item.id}>
                <button
                  className={`step ${active ? 'is-active' : ''} ${completed ? 'is-complete' : ''}`}
                  disabled={!canNavigate}
                  onClick={() => router.push(`/plan/${trip.id}/${item.id}`)}
                >
                  <span className="step__dot">{completed ? <Check size={12} /> : <Icon size={12} />}</span>
                  <span>{item.label}</span>
                </button>
                {index < steps.length - 1 && <span className={`step-line ${completed ? 'is-complete' : ''}`} />}
              </div>
            );
          })}
        </div>
        <div className="step-progress__mobile">
          <div className="mobile-dots">{steps.map((item, index) => <span key={item.id} className={index <= activeIndex ? 'is-filled' : ''} />)}</div>
          <strong>{activeIndex + 1}/{steps.length} {steps[activeIndex]?.label}</strong>
        </div>
      </nav>

      <main className="step-main">{children}</main>
      <footer className="step-footer">{footer}</footer>
    </div>
  );
}

export function BrandHeader() {
  useEffect(() => {
    const isDark = window.localStorage.getItem('voyagent:theme') === 'dark';
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
  }, []);
  const toggle = () => {
    const isDark = document.documentElement.dataset.theme !== 'dark';
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
    window.localStorage.setItem('voyagent:theme', isDark ? 'dark' : 'light');
  };
  return (
    <header className="brand-header">
      <Link href="/" className="wordmark"><span className="wordmark__mark"><Sparkles size={15} /></span> Voyagent</Link>
      <div className="brand-header__actions">
        <button className="key-hint" aria-label="명령 팔레트">⌘ K</button>
        <button className="icon-button" onClick={toggle} aria-label="테마 변경"><Moon size={17} /></button>
      </div>
    </header>
  );
}
