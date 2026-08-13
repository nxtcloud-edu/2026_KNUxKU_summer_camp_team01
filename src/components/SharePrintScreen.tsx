'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, BedDouble, CheckCircle2, Plane, Printer, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { BrandHeader } from '@/components/AppShell';
import { MapPanel } from '@/components/MapPanel';
import { CITIES, FLIGHTS, PLACES, STAYS } from '@/lib/data';
import { useTripStore } from '@/lib/store';
import type { Trip } from '@/lib/types';

export function SharePrintScreen({ mode }: { mode: 'share' | 'print' }) {
  const params = useParams<{ tripId: string }>();
  const stored = useTripStore((state) => state.trips[params.tripId]);
  const [snapshot, setSnapshot] = useState<Trip | null>(null);
  useEffect(() => {
    if (stored) return;
    const timer = window.setTimeout(() => {
      try {
        const raw = window.location.hash.slice(1);
        if (raw) setSnapshot(JSON.parse(decodeURIComponent(escape(window.atob(raw)))) as Trip);
      } catch {
        setSnapshot(null);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [stored]);
  const trip = stored ?? snapshot;
  const city = CITIES.find((item) => item.id === trip?.destinationId);
  const flight = FLIGHTS.find((item) => item.id === trip?.selectedFlightId);
  const stay = STAYS.find((item) => item.id === trip?.selectedStayId);
  const selectedPlaces = useMemo(() => trip ? PLACES.filter((place) => trip.selectedPlaceIds.includes(place.id)) : [], [trip]);

  if (!trip || !trip.itinerary) return <div className="share-empty"><Sparkles size={30} /><h1>일정을 불러올 수 없어요</h1><p>링크가 잘렸거나 아직 일정이 완성되지 않았어요.</p><Link href="/" className="button button--primary">홈으로</Link></div>;

  return (
    <div className={`readonly-page ${mode === 'print' ? 'print-page' : ''}`}>
      {mode === 'share' ? <BrandHeader /> : (
        <header className="print-toolbar no-print"><Link href={`/plan/${trip.id}/itinerary`} className="button button--secondary"><ArrowLeft size={16} /> 일정으로</Link><button className="button button--primary" onClick={() => window.print()}><Printer size={16} /> 인쇄하기</button></header>
      )}
      <section className="readonly-hero">
        <div><span className="eyebrow">{mode === 'share' ? '공유된 여행 일정' : 'VOYAGENT TRIP PLAN'}</span><h1>{city?.flag} {trip.title}</h1><p>{trip.startDate} – {trip.endDate} · 성인 {trip.persona.adults}명</p></div>
        {trip.verification && <span className="verification-seal"><CheckCircle2 size={16} /> 검증 완료</span>}
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
                const place = PLACES.find((value) => value.id === item.placeId);
                return <div className="readonly-item" key={item.id}><time>{item.time}</time><span className="readonly-item__number">{item.kind === 'place' ? index + 1 : '·'}</span><div><strong>{item.title}</strong><small>{place ? `${place.category} · ${place.area} · ${place.price}` : item.kind}</small>{item.travelMinutes && <em>다음 장소까지 {item.travelMode} {item.travelMinutes}분</em>}</div></div>;
              })}
            </section>
          ))}
        </div>
        {mode === 'share' && <aside><MapPanel selectedIds={selectedPlaces.map((place) => place.id)} showRoute stay={stay ?? null} /></aside>}
      </div>
      {mode === 'share' && <footer className="readonly-footer"><span>Voyagent로 만든 일정입니다.</span><Link href="/" className="button button--primary">나도 만들어보기</Link></footer>}
    </div>
  );
}
