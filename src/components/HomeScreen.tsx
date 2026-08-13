'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, CheckCircle2, Compass, MoreHorizontal, Search, Sparkles, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import { BrandHeader } from '@/components/AppShell';
import { CITIES } from '@/lib/data';
import { useTripStore } from '@/lib/store';
import messages from '../../messages/ko.json';

export function HomeScreen() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [selectedCity, setSelectedCity] = useState<string | null>(null);
  const trips = useTripStore((state) => state.trips);
  const removeTrip = useTripStore((state) => state.removeTrip);
  const hasHydrated = useTripStore((state) => state.hasHydrated);
  const tripList = useMemo(() => Object.values(trips).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)), [trips]);
  const filteredCities = CITIES.filter((city) => `${city.name} ${city.nameEn} ${city.country}`.toLowerCase().includes(query.toLowerCase()));
  const selected = CITIES.find((city) => city.id === selectedCity);

  const start = (cityId?: string) => router.push(`/plan/new${cityId ? `?city=${cityId}` : ''}`);

  return (
    <div className="home-page">
      <BrandHeader />
      <section className="home-hero">
        <div className="eyebrow"><Sparkles size={14} /> AI 여행 플래너</div>
        <h1>{messages.home.title1}<br /><span>{messages.home.title2}</span></h1>
        <p>{messages.home.description1}<br />{messages.home.description2}</p>
        <div className="quick-start">
          <div className="city-search">
            <Search size={18} />
            <input
              value={selected ? `${selected.flag} ${selected.name}` : query}
              onChange={(event) => { setSelectedCity(null); setQuery(event.target.value); }}
              onFocus={() => selected && setSelectedCity(null)}
              placeholder={messages.home.placeholder}
              aria-label={messages.home.placeholder}
            />
            {query && !selected && (
              <div className="city-search__menu">
                {filteredCities.map((city) => (
                  <button key={city.id} onClick={() => { setSelectedCity(city.id); setQuery(''); }}>
                    <span>{city.flag}</span><strong>{city.name}</strong><small>{city.country} · {city.nameEn}</small><em>데모 데이터</em>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button className="button button--primary button--large" onClick={() => start(selectedCity ?? undefined)}>
            {selected ? `${selected.name} 여행 시작` : messages.home.start}<ArrowRight size={17} />
          </button>
        </div>
        <div className="popular-cities"><span>{messages.home.popular}</span>{CITIES.map((city) => <button key={city.id} onClick={() => start(city.id)}>{city.flag} {city.name}</button>)}</div>
      </section>

      <section className="trip-section">
        <header><div><h2>{messages.home.myTrips}</h2><span>{tripList.length}개</span></div></header>
        {!hasHydrated ? (
          <div className="trip-grid">{[1, 2, 3].map((value) => <div className="trip-card trip-card--skeleton" key={value} />)}</div>
        ) : tripList.length === 0 ? (
          <div className="empty-state"><Compass size={38} /><h3>{messages.home.empty}</h3><p>{messages.home.emptyDescription}</p><button className="button button--primary" onClick={() => start()}>새 여행 시작<ArrowRight size={16} /></button></div>
        ) : (
          <div className="trip-grid">
            {tripList.map((trip) => {
              const city = CITIES.find((item) => item.id === trip.destinationId);
              const progress = Math.round((trip.completedSteps.length / 7) * 100);
              return (
                <article className="trip-card" key={trip.id}>
                  <Link href={`/plan/${trip.id}/${trip.currentStep}`} className="trip-card__link" aria-label={`${trip.title} 이어서 계획하기`}>
                    <div className="trip-card__image" style={{ backgroundImage: `url(${city?.image ?? 'https://picsum.photos/seed/new-trip/800/400'})` }}>
                      {trip.verification && <span className="verified-badge"><CheckCircle2 size={13} /> 검증 완료</span>}
                    </div>
                    <div className="trip-card__body">
                      <h3><span>{city?.flag ?? '·'}</span>{trip.title}</h3>
                      <p>{trip.startDate ? `${trip.startDate.slice(5)} – ${trip.endDate.slice(5)}` : '날짜 미정'}</p>
                      <div className="trip-progress"><span style={{ width: `${progress}%` }} /></div>
                      <div className="trip-card__meta"><span>{progress === 100 ? '완료' : trip.currentStep}</span><span>최근 저장됨</span></div>
                      <strong className="continue-label">이어서 <ArrowRight size={14} /></strong>
                    </div>
                  </Link>
                  <div className="trip-card__menu">
                    <button aria-label="여행 메뉴"><MoreHorizontal size={17} /></button>
                    <button className="delete-trip" onClick={() => removeTrip(trip.id)} aria-label="여행 삭제"><Trash2 size={15} /></button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
      <footer className="home-footer">{messages.home.footer}</footer>
    </div>
  );
}
