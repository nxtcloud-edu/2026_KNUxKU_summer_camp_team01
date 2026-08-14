'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, BedDouble, CheckCircle2, Copy, Plane, Printer, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { BrandHeader } from '@/components/AppShell';
import { MapPanel } from '@/components/MapPanel';
import { getTripDestination } from '@/lib/locations';
import { getTripFlight, getTripStay } from '@/lib/searchResults';
import { isVerificationCurrent } from '@/lib/itinerary';
import { getTripPlace, getTripPlaces } from '@/lib/places';
import { useTripStore } from '@/lib/store';
import type { Trip } from '@/lib/types';

type ReadonlyMode = 'result' | 'share' | 'print';

const encodeTrip = (trip: Trip) => window.btoa(unescape(encodeURIComponent(JSON.stringify(trip))));

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand('copy');
    textarea.remove();
    return copied;
  }
}

export function SharePrintScreen({ mode }: { mode: ReadonlyMode }) {
  const params = useParams<{ tripId: string }>();
  const stored = useTripStore((state) => state.trips[params.tripId]);
  const hasHydrated = useTripStore((state) => state.hasHydrated);
  const [snapshot, setSnapshot] = useState<Trip | null>(null);
  const [snapshotResolved, setSnapshotResolved] = useState(mode !== 'share');
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const savedTrip = stored?.savedAt && stored.itinerary ? stored : null;

  useEffect(() => {
    if (!hasHydrated || mode !== 'share' || savedTrip) return;
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
  }, [hasHydrated, mode, savedTrip]);

  useEffect(() => {
    if (!copyStatus) return;
    const timer = window.setTimeout(() => setCopyStatus(null), 2600);
    return () => window.clearTimeout(timer);
  }, [copyStatus]);

  const trip = savedTrip ?? (mode === 'share' ? snapshot : null);
  const city = trip ? getTripDestination(trip) : undefined;
  const flight = trip ? getTripFlight(trip, trip.selectedFlightId) : undefined;
  const stay = trip ? getTripStay(trip, trip.selectedStayId) : undefined;
  const allPlaces = useMemo(() => trip ? getTripPlaces(trip) : [], [trip]);
  const selectedPlaces = useMemo(() => trip ? allPlaces.filter((place) => trip.selectedPlaceIds.includes(place.id)) : [], [allPlaces, trip]);

  if ((!hasHydrated && !savedTrip) || (mode === 'share' && !savedTrip && !snapshotResolved)) {
    return <div className="page-loading"><Sparkles className="spin" size={24} /><span>일정을 불러오고 있어요</span></div>;
  }

  const copyShareUrl = async () => {
    if (!trip) return;
    const url = `${window.location.origin}/trip/${trip.id}/share#${encodeTrip(trip)}`;
    const copied = await copyText(url);
    setCopyStatus(copied ? '공유 링크를 복사했어요.' : '링크를 복사하지 못했어요. 브라우저 권한을 확인해 주세요.');
  };

  if (!trip || !trip.itinerary) {
    const isSavedResult = mode !== 'share';
    return <div className="share-empty"><Sparkles size={30} /><h1>{isSavedResult ? '저장된 일정을 찾을 수 없어요' : '일정을 불러올 수 없어요'}</h1><p>{isSavedResult ? 'URL이 올바른지 확인하거나, 일정을 저장한 브라우저에서 다시 열어 주세요.' : '링크가 잘렸거나 아직 일정이 완성되지 않았어요.'}</p><Link href="/" className="button button--primary">홈으로</Link></div>;
  }

  const heroLabel = mode === 'result' ? '저장된 여행 일정' : mode === 'share' ? '공유된 여행 일정' : 'VOYAGENT TRIP PLAN';

  return (
    <div className={`readonly-page ${mode === 'print' ? 'print-page' : ''}`}>
      {mode === 'print' ? (
        <header className="print-toolbar no-print"><Link href={`/trip/${trip.id}`} className="button button--secondary"><ArrowLeft size={16} /> 저장된 일정으로</Link><button className="button button--primary" onClick={() => window.print()}><Printer size={16} /> 인쇄하기</button></header>
      ) : <BrandHeader />}
      <section className="readonly-hero">
        <div><span className="eyebrow">{heroLabel}</span><h1>{city?.flag} {trip.title}</h1><p>{trip.startDate} – {trip.endDate} · 성인 {trip.persona.adults}명</p></div>
        <div className="readonly-hero__actions">
          {mode === 'result' && <Link href={`/trip/${trip.id}/present`} className="button button--primary"><Sparkles size={16} /> 일정 둘러보기</Link>}
          {isVerificationCurrent(trip) && <span className="verification-seal"><CheckCircle2 size={16} /> 검증 완료</span>}
        </div>
      </section>
      <div className="readonly-summary">
        {flight && <span><Plane size={16} /> {flight.airline} {flight.code} · {flight.outbound}</span>}
        {stay && <span><BedDouble size={16} /> {stay.name} · 4박</span>}
      </div>
      <div className="readonly-layout">
        <div className="readonly-days">
          {trip.itinerary.map((day, dayIndex) => (
            <section className="readonly-day" key={day.id}>
              <header><span>DAY {dayIndex + 1}</span><div><h2>{day.title}</h2><p>{day.date}</p></div></header>
              {day.items.map((item, index) => {
                const place = getTripPlace(trip, item.placeId ?? '');
                return <div className="readonly-item" key={item.id}><time>{item.time}</time><span className="readonly-item__number">{item.kind === 'place' ? index + 1 : '·'}</span><div><strong>{item.title}</strong><small>{place ? `${place.category} · ${place.area}${place.price ? ` · ${place.price}` : ''}` : item.kind}</small>{item.travelMinutes && <em>다음 장소까지 {item.travelMode} {item.travelMinutes}분</em>}</div></div>;
              })}
            </section>
          ))}
        </div>
        {mode !== 'print' && <aside><MapPanel places={allPlaces} selectedIds={selectedPlaces.map((place) => place.id)} showRoute stay={stay ?? null} /></aside>}
      </div>
      {mode === 'result' && <footer className="readonly-footer"><span>일정이 저장되었어요. 필요할 때 공유 링크를 복사하세요.</span><div className="footer-actions"><button className="button button--secondary" onClick={() => void copyShareUrl()}><Copy size={16} /> 공유 링크 복사</button><Link href={`/trip/${trip.id}/print`} className="button button--primary"><Printer size={16} /> 인쇄하기</Link></div>{copyStatus && <p className="notice-toast" role="status">{copyStatus}</p>}</footer>}
    </div>
  );
}
