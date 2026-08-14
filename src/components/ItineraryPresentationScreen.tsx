'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, ArrowRight, CalendarDays, CheckCircle2, Clock3, Navigation, PanelRightClose, PanelRightOpen, RotateCcw, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { MapPanel } from '@/components/MapPanel';
import { STAYS } from '@/lib/data';
import { getTripDestination } from '@/lib/locations';
import { getTripPlace, getTripPlaces } from '@/lib/places';
import { useTripStore } from '@/lib/store';
import type { ItineraryItem, Trip } from '@/lib/types';

type PresentationDay = {
  id: string;
  title: string;
  date: string;
  dayNumber: number;
  items: ItineraryItem[];
};

const durationLabel = (minutes: number) => {
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  if (!hours) return `${remaining}분`;
  return remaining ? `${hours}시간 ${remaining}분` : `${hours}시간`;
};

export function ItineraryPresentationScreen() {
  const params = useParams<{ tripId: string }>();
  const stored = useTripStore((state) => state.trips[params.tripId]);
  const hasHydrated = useTripStore((state) => state.hasHydrated);
  const [snapshot, setSnapshot] = useState<Trip | null>(null);
  const [snapshotResolved, setSnapshotResolved] = useState(false);
  const [activeDayIndex, setActiveDayIndex] = useState(0);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [finished, setFinished] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(true);

  useEffect(() => {
    if (!hasHydrated || stored?.savedAt) return;
    const timer = window.setTimeout(() => {
      try {
        const raw = window.location.hash.slice(1);
        setSnapshot(raw ? JSON.parse(decodeURIComponent(escape(window.atob(raw)))) as Trip : null);
      } catch {
        setSnapshot(null);
      } finally {
        setSnapshotResolved(true);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [hasHydrated, stored?.savedAt]);

  const trip = stored?.savedAt && stored.itinerary ? stored : snapshot;
  const days = useMemo<PresentationDay[]>(() => trip?.itinerary?.map((day, dayIndex) => ({
    id: day.id,
    title: day.title,
    date: day.date,
    dayNumber: dayIndex + 1,
    items: day.items.filter((item) => item.kind === 'place' && item.placeId),
  })).filter((day) => day.items.length > 0) ?? [], [trip]);

  const activeDay = days[activeDayIndex];
  const activeItem = activeDay?.items[activeStepIndex];
  const allPlaces = useMemo(() => trip ? getTripPlaces(trip) : [], [trip]);
  const activePlace = trip ? getTripPlace(trip, activeItem?.placeId ?? '') : undefined;
  const city = trip ? getTripDestination(trip) : undefined;
  const stay = STAYS.find((item) => item.id === trip?.selectedStayId) ?? null;
  const dayPlaceIds = activeDay?.items.flatMap((item) => item.placeId ? [item.placeId] : []) ?? [];
  const currentStepNumber = days.slice(0, activeDayIndex).reduce((count, day) => count + day.items.length, 0) + activeStepIndex + 1;
  const totalSteps = days.reduce((count, day) => count + day.items.length, 0);
  const atFirst = activeDayIndex === 0 && activeStepIndex === 0;
  const atLast = activeDayIndex === days.length - 1 && activeStepIndex === (activeDay?.items.length ?? 1) - 1;

  const selectDay = (dayIndex: number) => {
    setActiveDayIndex(dayIndex);
    setActiveStepIndex(0);
    setFinished(false);
    setDrawerOpen(true);
  };

  const previous = () => {
    setFinished(false);
    setDrawerOpen(true);
    if (activeStepIndex > 0) return setActiveStepIndex((index) => index - 1);
    if (activeDayIndex > 0) {
      setActiveDayIndex((index) => index - 1);
      setActiveStepIndex(days[activeDayIndex - 1].items.length - 1);
    }
  };

  const next = () => {
    if (atLast) return setFinished(true);
    setFinished(false);
    setDrawerOpen(true);
    if (activeStepIndex < (activeDay?.items.length ?? 0) - 1) return setActiveStepIndex((index) => index + 1);
    setActiveDayIndex((index) => index + 1);
    setActiveStepIndex(0);
  };

  if (!hasHydrated || (!stored?.savedAt && !snapshotResolved)) {
    return <div className="page-loading"><Sparkles className="spin" size={24} /><span>저장된 일정을 불러오고 있어요</span></div>;
  }

  if (!trip || !trip.itinerary || days.length === 0) {
    return <div className="share-empty"><Sparkles size={30} /><h1>둘러볼 일정을 불러올 수 없어요</h1><p>장소가 포함된 일정이 완성된 뒤 다시 시도해 주세요.</p><Link href={`/trip/${params.tripId}`} className="button button--primary">전체 일정으로</Link></div>;
  }

  return (
    <main className="presentation-page presentation-page--fullscreen">
      <section className="presentation-map" aria-label="일정 지도">
        <MapPanel
          places={allPlaces}
          selectedIds={dayPlaceIds}
          activeId={activeItem?.placeId ?? null}
          onMarkerClick={(id) => {
            const index = activeDay.items.findIndex((item) => item.placeId === id);
            if (index >= 0) {
              setActiveStepIndex(index);
              setFinished(false);
              setDrawerOpen(true);
            }
          }}
          showRoute
          stay={stay}
          focusActive
        />
      </section>

      <header className="presentation-topbar">
        <Link href={`/trip/${trip.id}`} className="presentation-exit"><ArrowLeft size={17} /><span>전체 일정</span></Link>
        <div className="presentation-trip-label"><span>ITINERARY SIMULATION</span><strong>{city?.flag} {trip.title}</strong></div>
        <div className="presentation-topbar__actions">
          <span className="presentation-counter" aria-label={`전체 ${totalSteps}개 중 ${currentStepNumber}번째 장소`}>{currentStepNumber} / {totalSteps}</span>
          <button className="presentation-drawer-toggle" type="button" onClick={() => setDrawerOpen((open) => !open)} aria-controls="presentation-drawer" aria-expanded={drawerOpen} aria-label={drawerOpen ? '장소 정보 접기' : '장소 정보 열기'}>
            {drawerOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
          </button>
        </div>
      </header>

      <nav className="presentation-days" aria-label="일차 선택">
        {days.map((day, index) => <button type="button" key={day.id} className={index === activeDayIndex ? 'is-active' : ''} aria-current={index === activeDayIndex ? 'step' : undefined} onClick={() => selectDay(index)}><span>DAY {day.dayNumber}</span><strong>{day.title}</strong></button>)}
      </nav>

      <aside id="presentation-drawer" className={`presentation-drawer ${drawerOpen ? 'is-open' : ''}`} aria-live="polite" aria-label="현재 장소 정보">
        <button className="presentation-drawer__handle" type="button" onClick={() => setDrawerOpen((open) => !open)} aria-label={drawerOpen ? '장소 정보 접기' : '장소 정보 열기'}><span /></button>
        <div className="presentation-card">
          <div className="presentation-card__meta"><span>DAY {activeDay.dayNumber}</span><span>{activeDay.date}</span><span>{activeStepIndex + 1}번째 장소</span></div>
          <div className="presentation-card__heading">
            <span className="presentation-place-number">{currentStepNumber}</span>
            <div><p>{activePlace?.category ?? '여행지'} · {activePlace?.area}</p><h1>{activeItem.title}</h1></div>
          </div>
          <p className="presentation-description">{activePlace?.summary ?? '여행 일정에 등록된 장소입니다.'}</p>
          <dl className="presentation-facts">
            <div><dt><Clock3 size={15} /> 도착 예상 시간</dt><dd>{activeItem.time}</dd></div>
            <div><dt><CalendarDays size={15} /> 체류 시간</dt><dd>{durationLabel(activeItem.duration)}</dd></div>
            {activeItem.travelMinutes && <div><dt><Navigation size={15} /> 다음 장소 이동</dt><dd>{activeItem.travelMode ?? '이동'} · {activeItem.travelMinutes}분</dd></div>}
          </dl>
          {activeItem.travelMinutes && <div className="presentation-travel"><Navigation size={17} /><span>이 장소를 둘러본 뒤 <strong>{activeItem.travelMode ?? '이동'}</strong>으로 약 <strong>{activeItem.travelMinutes}분</strong> 이동해 다음 일정으로 이어집니다.</span></div>}

          {finished ? (
            <div className="presentation-finish"><CheckCircle2 size={24} /><div><strong>모든 일정을 둘러봤어요.</strong><p>이제 전체 일정에서 세부 내용을 다시 확인할 수 있어요.</p></div><Link href={`/trip/${trip.id}`} className="button button--primary">전체 일정으로 돌아가기</Link></div>
          ) : (
            <div className="presentation-controls">
              <button className="button button--secondary" onClick={previous} disabled={atFirst}><ArrowLeft size={17} /> 이전</button>
              <button className="button button--primary" onClick={next}>{atLast ? <>마지막 일정 완료 <CheckCircle2 size={17} /></> : <>다음 장소 <ArrowRight size={17} /></>}</button>
            </div>
          )}
        </div>
      </aside>

      <button className="presentation-restart" type="button" onClick={() => selectDay(0)}><RotateCcw size={15} /><span>처음부터</span></button>
    </main>
  );
}
