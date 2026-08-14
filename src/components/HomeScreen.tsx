'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, CheckCircle2, Compass, MoreHorizontal, Search, Sparkles, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import { BrandHeader } from '@/components/AppShell';
import { getCityById, isDemoCity, searchCities } from '@/lib/cities';
import { CITIES, ORIGIN_CITIES } from '@/lib/data';
import { isVerificationCurrent } from '@/lib/itinerary';
import { useTripStore } from '@/lib/store';
import type { City } from '@/lib/types';
import messages from '../../messages/ko.json';

function LocationSearch({ options, query, selected, placeholder, onQueryChange, onSelect }: {
  options: City[];
  query: string;
  selected: City | null;
  placeholder: string;
  onQueryChange: (value: string) => void;
  onSelect: (location: City | null) => void;
}) {
  const results = query.trim() ? searchCities(query, 20).filter((item) => options.some((option) => option.id === item.id)) : [];

  return (
    <div className="city-search">
      <Search size={18} />
      <input
        value={selected ? `${selected.flag} ${selected.name}` : query}
        onChange={(event) => { onSelect(null); onQueryChange(event.target.value); }}
        onFocus={() => { if (selected) { onSelect(null); onQueryChange(''); } }}
        placeholder={placeholder}
        aria-label={placeholder}
      />
      {query && !selected && results.length > 0 && (
        <div className="city-search__menu">
          {results.map((item) => (
            <button key={item.id} onClick={() => { onSelect(item); onQueryChange(''); }}>
              <span>{item.flag}</span><strong>{item.name}</strong><small>{item.country} · {item.airportCodes.join(' · ')}</small>{isDemoCity(item) && <em>체험 데이터</em>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function HomeScreen() {
  const router = useRouter();
  const [originQuery, setOriginQuery] = useState('');
  const [destinationQuery, setDestinationQuery] = useState('');
  const [selectedOrigin, setSelectedOrigin] = useState<City | null>(null);
  const [selectedCity, setSelectedCity] = useState<City | null>(null);
  const trips = useTripStore((state) => state.trips);
  const removeTrip = useTripStore((state) => state.removeTrip);
  const hasHydrated = useTripStore((state) => state.hasHydrated);
  const tripList = useMemo(() => Object.values(trips).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)), [trips]);

  const start = () => {
    const params = new URLSearchParams();
    if (selectedOrigin) params.set('origin', selectedOrigin.id);
    if (selectedCity) params.set('city', selectedCity.id);
    if (selectedOrigin || selectedCity) {
      sessionStorage.setItem('voyagent:pending-locations', JSON.stringify({ origin: selectedOrigin, destination: selectedCity }));
    }
    router.push(`/plan/new${params.size ? `?${params.toString()}` : ''}`);
  };

  return (
    <div className="home-page">
      <BrandHeader />
      <section className="home-hero">
        <div className="eyebrow"><Sparkles size={14} /> AI 여행 플래너</div>
        <h1>{messages.home.title1}<br /><span>{messages.home.title2}</span></h1>
        <p>{messages.home.description1}<br />{messages.home.description2}</p>
        <div className="quick-start">
          <LocationSearch options={ORIGIN_CITIES} query={originQuery} selected={selectedOrigin} placeholder={messages.home.originPlaceholder} onQueryChange={setOriginQuery} onSelect={setSelectedOrigin} />
          <LocationSearch options={CITIES} query={destinationQuery} selected={selectedCity} placeholder={messages.home.placeholder} onQueryChange={setDestinationQuery} onSelect={setSelectedCity} />
          <button
            aria-label={selectedOrigin && selectedCity ? `${selectedOrigin.name}에서 ${selectedCity.name} 여행 계획 짜기` : messages.home.start}
            className="button button--primary button--large"
            onClick={() => start()}
          >
            {messages.home.start}<ArrowRight size={16} />
          </button>
        </div>
        <div className="popular-cities"><span>{messages.home.popular}</span>{CITIES.map((city) => <button key={city.id} onClick={() => { setSelectedCity(city); setDestinationQuery(''); }}>{city.flag} {city.name}</button>)}</div>
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
              const origin = getCityById(trip.originId);
              const city = getCityById(trip.destinationId);
              const progress = Math.round((trip.completedSteps.length / 7) * 100);
              return (
                <article className="trip-card" key={trip.id}>
                  <Link href={`/plan/${trip.id}/${trip.currentStep}`} className="trip-card__link" aria-label={`${trip.title} 이어서 계획하기`}>
                    <div className="trip-card__image" style={{ backgroundImage: `url(${city?.image ?? 'https://picsum.photos/seed/new-trip/800/400'})` }}>
                      {isVerificationCurrent(trip) && <span className="verified-badge"><CheckCircle2 size={13} /> 검증 완료</span>}
                    </div>
                    <div className="trip-card__body">
                      <h3><span>{city?.flag ?? '·'}</span>{trip.title}</h3>
                      <p>{origin ? `${origin.name} → ${city?.name ?? '목적지 미정'} · ` : ''}{trip.startDate ? `${trip.startDate.slice(5)} – ${trip.endDate.slice(5)}` : '날짜 미정'}</p>
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
