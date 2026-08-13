'use client';

import { useParams, useRouter, useSearchParams } from 'next/navigation';
import {
  Accessibility,
  ArrowLeft,
  ArrowRight,
  BedDouble,
  BriefcaseBusiness,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock3,
  Coffee,
  Footprints,
  GripVertical,
  Heart,
  Hotel,
  Landmark,
  Link2,
  ListChecks,
  Loader2,
  MapPin,
  Minus,
  Navigation,
  Plane,
  Plus,
  Search,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Star,
  TrainFront,
  Trees,
  TriangleAlert,
  User,
  Users,
  UtensilsCrossed,
  WandSparkles,
} from 'lucide-react';
import { useEffect, useState } from 'react';

import { AgentPanel } from '@/components/AgentPanel';
import { AppShell } from '@/components/AppShell';
import { MapPanel } from '@/components/MapPanel';
import { CITIES, FLIGHTS, INTERESTS, ORIGIN_CITIES, PLACES, STAYS } from '@/lib/data';
import { useTripStore } from '@/lib/store';
import type { StepId, Trip } from '@/lib/types';
import messages from '../../messages/ko.json';

const STEP_ORDER: StepId[] = ['city', 'persona', 'flights', 'stays', 'places', 'itinerary', 'verify'];
const STEP_LABELS: Record<StepId, string> = {
  city: '도시', persona: '여행 스타일', flights: '항공권', stays: '숙소', places: '가고 싶은 곳', itinerary: '일정', verify: '검증',
};

function applicableSteps(trip: Trip) {
  return STEP_ORDER.filter((step) =>
    (step !== 'flights' || trip.persona.includeFlights !== false) &&
    (step !== 'stays' || trip.persona.includeStays !== false));
}

export function PlannerScreen({ step }: { step: StepId }) {
  const params = useParams<{ tripId: string }>();
  const router = useRouter();
  const tripId = params.tripId;
  const trip = useTripStore((state) => state.trips[tripId]);
  const ensureTrip = useTripStore((state) => state.ensureTrip);
  const completeStep = useTripStore((state) => state.completeStep);
  const updateTrip = useTripStore((state) => state.updateTrip);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => ensureTrip(tripId), [ensureTrip, tripId]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 2600);
    return () => window.clearTimeout(timer);
  }, [notice]);

  if (!trip) return <div className="page-loading"><Loader2 className="spin" size={24} /><span>여행을 불러오고 있어요</span></div>;

  const steps = applicableSteps(trip);
  const index = steps.indexOf(step);
  const previous = index > 0 ? steps[index - 1] : null;
  const next = index < steps.length - 1 ? steps[index + 1] : null;

  const goNext = () => {
    if (step === 'city' && !trip.originId) return setNotice('출발 도시를 선택해 주세요');
    if (step === 'city' && !trip.destinationId) return setNotice('여행할 도시를 선택해 주세요');
    if (step === 'city' && (!trip.startDate || !trip.endDate)) return setNotice('여행 날짜를 선택해 주세요');
    if (step === 'persona' && trip.persona.includeFlights === null) return setNotice('항공권을 함께 찾을지 선택해 주세요');
    if (step === 'persona' && trip.persona.includeStays === null) return setNotice('숙소를 함께 찾을지 선택해 주세요');
    if (step === 'persona' && !trip.persona.companion) return setNotice('누구와 함께 가는지 선택해 주세요');
    if (step === 'persona' && trip.persona.interests.length === 0) return setNotice('관심 있는 활동을 1개 이상 선택해 주세요');
    if (step === 'flights' && !trip.selectedFlightId) return setNotice('항공권을 선택하거나 이 단계를 건너뛰어 주세요');
    if (step === 'stays' && !trip.selectedStayId) return setNotice('숙소를 선택하거나 이 단계를 건너뛰어 주세요');
    if (step === 'places' && trip.selectedPlaceIds.length === 0) return setNotice('가고 싶은 곳을 1곳 이상 선택해 주세요');
    if (step === 'itinerary' && !trip.itinerary) return setNotice('일정을 먼저 생성해 주세요');
    if (step === 'verify') return router.push(`/trip/${tripId}/share`);
    if (next) {
      completeStep(tripId, step, next);
      router.push(`/plan/${tripId}/${next}`);
    }
  };

  const skip = () => {
    if (step !== 'flights' && step !== 'stays') return;
    const skipNext: StepId = step === 'flights' && trip.persona.includeStays ? 'stays' : 'places';
    updateTrip(tripId, step === 'flights' ? { selectedFlightId: 'skipped' } : { selectedStayId: 'skipped' });
    completeStep(tripId, step, skipNext);
    router.push(`/plan/${tripId}/${skipNext}`);
  };

  const footer = (
    <div className="step-footer__inner">
      <div>{previous && <button className="button button--secondary" onClick={() => router.push(`/plan/${tripId}/${previous}`)}><ArrowLeft size={16} /> 이전</button>}</div>
      <div className="footer-actions">
        {(step === 'flights' || step === 'stays') && <button className="button button--ghost" onClick={skip}>이 단계 건너뛰기</button>}
        <button className="button button--primary" onClick={goNext}>
          {step === 'verify' ? '일정 공유하기' : `다음: ${next ? STEP_LABELS[next] : ''}`}<ArrowRight size={16} />
        </button>
      </div>
    </div>
  );

  return (
    <AppShell trip={trip} step={step} footer={footer}>
      {notice && <div className="notice-toast" role="alert"><CircleAlert size={16} />{notice}</div>}
      {step === 'city' && <CityStep trip={trip} update={(patch) => updateTrip(tripId, patch)} />}
      {step === 'persona' && <PersonaStep trip={trip} update={(patch) => updateTrip(tripId, patch)} />}
      {step === 'flights' && <FlightsStep trip={trip} update={(patch) => updateTrip(tripId, patch)} />}
      {step === 'stays' && <StaysStep trip={trip} update={(patch) => updateTrip(tripId, patch)} />}
      {step === 'places' && <PlacesStep trip={trip} />}
      {step === 'itinerary' && <ItineraryStep trip={trip} />}
      {step === 'verify' && <VerifyStep trip={trip} />}
    </AppShell>
  );
}

function PageHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <header className="page-heading"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></header>;
}

function CityStep({ trip, update }: { trip: Trip; update: (patch: Partial<Trip>) => void }) {
  const searchParams = useSearchParams();
  const [originQuery, setOriginQuery] = useState('');
  const [destinationQuery, setDestinationQuery] = useState('');
  const [originMenuOpen, setOriginMenuOpen] = useState(!trip.originId);
  const [destinationMenuOpen, setDestinationMenuOpen] = useState(!trip.destinationId);
  const origin = ORIGIN_CITIES.find((item) => item.id === trip.originId);
  const city = CITIES.find((item) => item.id === trip.destinationId);
  const filteredOrigins = ORIGIN_CITIES.filter((item) => `${item.name} ${item.nameEn} ${item.airportCodes.join(' ')}`.toLowerCase().includes(originQuery.toLowerCase()));
  const filteredDestinations = CITIES.filter((item) => `${item.name} ${item.nameEn} ${item.country} ${item.airportCodes.join(' ')}`.toLowerCase().includes(destinationQuery.toLowerCase()));
  const routeReady = Boolean(origin && city);

  useEffect(() => {
    const originId = searchParams.get('origin');
    const cityId = searchParams.get('city');
    const targetOrigin = ORIGIN_CITIES.find((item) => item.id === originId);
    const targetCity = CITIES.find((item) => item.id === cityId);
    const patch: Partial<Trip> = {};
    if (targetOrigin && !trip.originId) patch.originId = targetOrigin.id;
    if (targetCity && !trip.destinationId) {
      patch.destinationId = targetCity.id;
      patch.title = `${targetCity.name} 여행`;
    }
    if (Object.keys(patch).length > 0) update(patch);
  }, [searchParams, trip.destinationId, trip.originId, update]);

  const selectOrigin = (id: string) => {
    update({ originId: id, selectedFlightId: null, itinerary: null, verification: null });
    setOriginMenuOpen(false);
    setOriginQuery('');
  };

  const selectDestination = (id: string) => {
    const selected = CITIES.find((item) => item.id === id);
    update({ destinationId: id, title: `${selected?.name ?? '새'} 여행`, selectedFlightId: null, selectedStayId: null, selectedPlaceIds: [], itinerary: null, verification: null });
    setDestinationMenuOpen(false);
    setDestinationQuery('');
  };

  return (
    <div className="form-page">
      <PageHeading eyebrow="STEP 1 · 여행의 시작" title={messages.city.title} description={messages.city.description} />
      <section className="form-section">
        <div className="field-label"><span>{messages.city.origin}</span>{origin && <Check size={14} />}</div>
        {origin && !originMenuOpen ? (
          <div className="city-hero" style={{ backgroundImage: `url(${origin.image})` }}>
            <div><strong><span>{origin.flag}</span>{origin.name}</strong><small>{origin.country} · {origin.airportCodes.join(' · ')} · {origin.timezone}</small></div>
            <button className="button button--glass" onClick={() => setOriginMenuOpen(true)}>변경</button>
          </div>
        ) : (
          <div className="city-combobox">
            <div className="input-with-icon"><Search size={17} /><input autoFocus value={originQuery} onChange={(event) => setOriginQuery(event.target.value)} placeholder={messages.city.chooseOrigin} /></div>
            <div className="city-options">
              <span className="option-group">{originQuery ? '검색 결과' : '출발 도시'}</span>
              {filteredOrigins.map((item, index) => <button key={item.id} className={index === 0 ? 'is-active' : ''} onClick={() => selectOrigin(item.id)}><span>{item.flag}</span><strong>{item.name}</strong><small>{item.airportCodes.join(' · ')}</small><em>데모 데이터</em></button>)}
            </div>
          </div>
        )}
      </section>
      <section className="form-section">
        <div className="field-label"><span>{messages.city.destination}</span>{city && <Check size={14} />}</div>
        {city && !destinationMenuOpen ? (
          <div className="city-hero" style={{ backgroundImage: `url(${city.image})` }}>
            <div><strong><span>{city.flag}</span>{city.name}</strong><small>{city.country} · {city.airportCodes.join(' · ')} · {city.timezone}</small></div>
            <button className="button button--glass" onClick={() => setDestinationMenuOpen(true)}>변경</button>
          </div>
        ) : (
          <div className="city-combobox">
            <div className="input-with-icon"><Search size={17} /><input value={destinationQuery} onChange={(event) => setDestinationQuery(event.target.value)} placeholder={messages.city.chooseCity} /></div>
            <div className="city-options">
              <span className="option-group">{destinationQuery ? '검색 결과' : '인기 도시'}</span>
              {filteredDestinations.map((item, index) => <button key={item.id} className={index === 0 ? 'is-active' : ''} onClick={() => selectDestination(item.id)}><span>{item.flag}</span><strong>{item.name}</strong><small>{item.country} · {item.nameEn}</small><em>데모 데이터</em></button>)}
            </div>
          </div>
        )}
      </section>
      <section className={`form-section ${!routeReady ? 'is-disabled' : ''}`}>
        <div className="field-label"><span>{messages.city.date}</span>{trip.startDate && trip.endDate && <em>{getNights(trip.startDate, trip.endDate)}박 {getNights(trip.startDate, trip.endDate) + 1}일</em>}</div>
        <div className="date-card">
          <div><CalendarDays size={18} /><label>가는 날<input type="date" disabled={!routeReady} value={trip.startDate} min={new Date().toISOString().slice(0, 10)} onChange={(event) => update({ startDate: event.target.value, endDate: trip.endDate && trip.endDate < event.target.value ? '' : trip.endDate })} /></label></div>
          <ArrowRight size={16} />
          <div><CalendarDays size={18} /><label>돌아오는 날<input type="date" disabled={!routeReady || !trip.startDate} value={trip.endDate} min={trip.startDate} onChange={(event) => update({ endDate: event.target.value })} /></label></div>
        </div>
        {trip.startDate && trip.endDate ? <div className="date-summary"><CheckCircle2 size={16} /><div><strong>{trip.startDate} → {trip.endDate}</strong><span>{getNights(trip.startDate, trip.endDate)}박 {getNights(trip.startDate, trip.endDate) + 1}일 여행</span></div></div> : <p className="field-hint">{routeReady ? messages.city.chooseDate : '출발지와 목적지를 먼저 선택해 주세요'}</p>}
      </section>
    </div>
  );
}

function PersonaStep({ trip, update }: { trip: Trip; update: (patch: Partial<Trip>) => void }) {
  const persona = trip.persona;
  const requiredDone = [persona.includeFlights !== null, persona.includeStays !== null, Boolean(persona.companion), persona.interests.length > 0].filter(Boolean).length;
  const patchPersona = (patch: Partial<Trip['persona']>) => update({ persona: { ...persona, ...patch } });
  const companions = [{ id: 'solo', label: '혼자', icon: User }, { id: 'couple', label: '연인', icon: Heart }, { id: 'family', label: '가족', icon: Users }, { id: 'friends', label: '친구', icon: Users }, { id: 'work', label: '동료', icon: BriefcaseBusiness }];
  return (
    <div className="form-page">
      <PageHeading eyebrow="STEP 2 · 취향 설정" title={messages.persona.title} description={messages.persona.description} />
      <div className="persona-progress"><div><span style={{ width: `${requiredDone * 25}%` }} /></div><strong>필수 4개 중 {requiredDone}개 완료</strong></div>
      <section className="persona-section"><div className="section-divider"><span>함께 찾을 것</span></div><Question title="항공권을 함께 찾아드릴까요?" done={persona.includeFlights !== null}><div className="choice-grid choice-grid--two"><ChoiceCard selected={persona.includeFlights === true} onClick={() => patchPersona({ includeFlights: true })} icon={<Plane />} title="네, 찾아주세요" description="조건에 맞는 왕복 항공권을 비교해요" /><ChoiceCard selected={persona.includeFlights === false} onClick={() => patchPersona({ includeFlights: false })} icon={<CircleX />} title="아니요, 괜찮아요" description="이미 예약했거나 직접 알아볼게요" /></div></Question><Question title="숙소를 함께 찾아드릴까요?" done={persona.includeStays !== null}><div className="choice-grid choice-grid--two"><ChoiceCard selected={persona.includeStays === true} onClick={() => patchPersona({ includeStays: true })} icon={<Hotel />} title="네, 찾아주세요" description="위치와 예산을 비교해 추천해요" /><ChoiceCard selected={persona.includeStays === false} onClick={() => patchPersona({ includeStays: false })} icon={<CircleX />} title="아니요, 괜찮아요" description="이미 정한 숙소를 기준으로 계획해요" /></div></Question></section>
      <section className="persona-section"><div className="section-divider"><span>누구와, 어떻게</span></div><Question title="누구와 함께 가세요?" done={Boolean(persona.companion)}><div className="choice-grid choice-grid--five">{companions.map(({ id, label, icon: Icon }) => <button key={id} className={`compact-choice ${persona.companion === id ? 'is-selected' : ''}`} onClick={() => patchPersona({ companion: id })}><Icon size={19} /><span>{label}</span>{persona.companion === id && <Check size={13} />}</button>)}</div></Question><Question title="인원은 몇 명인가요?" done><div className="counter-row"><div><strong>성인</strong><span>13세 이상</span></div><div><button onClick={() => patchPersona({ adults: Math.max(1, persona.adults - 1) })}><Minus size={14} /></button><strong>{persona.adults}</strong><button onClick={() => patchPersona({ adults: Math.min(20, persona.adults + 1) })}><Plus size={14} /></button></div></div></Question><Question title="여행 페이스는 어떻게 할까요?" done><div className="choice-grid choice-grid--three">{([['relaxed', '여유롭게', '하루 2–3곳'], ['balanced', '적당히', '하루 3–4곳'], ['packed', '빽빽하게', '하루 5곳 이상']] as const).map(([id, label, detail]) => <button key={id} className={`pace-card ${persona.pace === id ? 'is-selected' : ''}`} onClick={() => patchPersona({ pace: id })}><strong>{label}</strong><span>{detail}</span><small>{id === 'relaxed' ? '이동 최소화' : id === 'balanced' ? '균형 잡힌 일정' : '최대한 많이'}</small></button>)}</div></Question><Question title="어떤 걸 좋아하세요?" done={persona.interests.length > 0} meta={`${persona.interests.length}개 선택`}><div className="interest-list">{INTERESTS.map((interest, index) => { const selected = persona.interests.includes(interest); const icons = [UtensilsCrossed, Coffee, Trees, Landmark, Landmark, ShoppingBag, Star, Navigation, MapPin, Accessibility]; const Icon = icons[index]; return <button key={interest} className={selected ? 'is-selected' : ''} onClick={() => patchPersona({ interests: selected ? persona.interests.filter((item) => item !== interest) : [...persona.interests, interest] })}><Icon size={15} />{interest}{selected && <Check size={13} />}</button>; })}</div></Question></section>
      <details className="advanced-section"><summary><ChevronDown size={16} /><div><strong>더 자세히 알려주기</strong><span>이동 수단 · 고려사항 · 예산 · 메모</span></div><em>선택</em></summary><div className="advanced-content"><label>추가 요청<textarea placeholder="예: 많이 걷지 않으면서 현지 음식을 즐기고 싶어요." /></label><div className="preference-row"><span><Footprints size={16} /> 도보 이동 선호</span><span><TrainFront size={16} /> 대중교통 선호</span></div></div></details>
    </div>
  );
}

function Question({ title, done, meta, children }: { title: string; done?: boolean; meta?: string; children: React.ReactNode }) {
  return <div className="question"><div className="question__title"><strong>{title}</strong><span>{meta}{done && <Check size={14} />}</span></div>{children}</div>;
}

function ChoiceCard({ selected, onClick, icon, title, description }: { selected: boolean; onClick: () => void; icon: React.ReactNode; title: string; description: string }) {
  return <button className={`choice-card ${selected ? 'is-selected' : ''}`} onClick={onClick}><span>{icon}</span><div><strong>{title}</strong><small>{description}</small></div>{selected && <CircleCheck size={17} />}</button>;
}

function FlightsStep({ trip, update }: { trip: Trip; update: (patch: Partial<Trip>) => void }) {
  const [phase, setPhase] = useState<'survey' | 'searching' | 'results'>(trip.selectedFlightId && trip.selectedFlightId !== 'skipped' ? 'results' : 'survey');
  const origin = ORIGIN_CITIES.find((item) => item.id === trip.originId);
  const destination = CITIES.find((item) => item.id === trip.destinationId);
  const availableFlights = FLIGHTS.filter((flight) => flight.originId === trip.originId && flight.destinationId === trip.destinationId);
  useEffect(() => {
    if (phase !== 'searching') return;
    const timer = window.setTimeout(() => setPhase('results'), 2300);
    return () => window.clearTimeout(timer);
  }, [phase]);
  if (phase === 'searching') return <div className="stream-page"><PageHeading eyebrow="AGENT · FLIGHT SEARCH" title="조건에 맞는 항공권을 비교하고 있어요" description="검색 과정과 판단 근거를 실시간으로 보여드릴게요." /><AgentPanel type="항공권" /><SkeletonCards count={3} /></div>;
  if (phase === 'survey') return <div className="form-page"><PageHeading eyebrow="STEP 3 · 항공권" title="항공권을 찾기 전에" description="조건을 알려주시면 맞는 것만 골라드려요. 모두 선택 사항이에요." /><div className="route-summary"><Plane size={20} /><div><strong>{origin?.name ?? '출발지'} ({origin?.airportCodes.join(' · ') ?? '-'}) → {destination?.name ?? '목적지'} ({destination?.airportCodes.join(' · ') ?? '-'})</strong><span>{trip.startDate} 출발 · {trip.endDate} 귀국 · 성인 {trip.persona.adults}명</span></div><button>수정</button></div><div className="survey-fields"><Question title="도착 공항"><div className="interest-list">{destination?.airportCodes.map((code) => <button className="is-selected" key={code}>{destination.name} {code} <Check size={13} /></button>)}</div></Question><Question title="경유"><div className="segmented"><button className="is-active">직항만</button><button>경유도 괜찮아요</button></div></Question><Question title="가는 날 출발 시간대" meta="1개 선택"><div className="interest-list"><button>새벽 00–06</button><button className="is-selected">오전 06–12</button><button>오후 12–18</button><button>저녁 18–24</button></div></Question><Question title="선호 항공사" meta="전체 12개"><div className="airline-box"><div><span>KE</span> 대한항공 <Check size={14} /></div><div><span>OZ</span> 아시아나항공</div><div><span>JL</span> 일본항공 <Check size={14} /></div><div><span>NH</span> 전일본공수</div></div></Question><Question title="1인당 가격 상한"><input className="range" type="range" min="280000" max="950000" defaultValue="900000" /><div className="range-labels"><span>28만원</span><strong>90만원</strong><span>95만원</span></div></Question></div><button className="button button--primary button--wide" onClick={() => setPhase('searching')}><Sparkles size={16} /> 항공권 찾기</button></div>;
  if (availableFlights.length === 0) return <div className="form-page"><PageHeading eyebrow="STEP 3 · 항공권" title="이 노선의 데모 항공편이 아직 없어요" description={`${origin?.name ?? '출발지'}에서 ${destination?.name ?? '목적지'}로 가는 항공편 데이터는 준비 중입니다.`} /><div className="empty-state"><Plane size={36} /><h3>다른 노선을 선택하거나 이 단계를 건너뛰어 주세요</h3><p>현재 항공권 목데이터는 서울 → 도쿄 노선을 지원합니다.</p><button className="button button--secondary" onClick={() => setPhase('survey')}>검색 조건 다시 보기</button></div></div>;
  return <div className="results-page"><div className="agent-summary"><Sparkles size={15} /><strong>{availableFlights.length}개 항공권을 찾았어요.</strong><span>가격과 첫날 활용도를 고려하면 대한항공이 가장 균형이 좋아요.</span><button>추론 보기</button></div><div className="results-toolbar"><div className="segmented"><button className="is-active">추천순</button><button>최저가</button><button>최단시간</button></div><span>{availableFlights.length}개 표시</span></div><div className="flight-list">{availableFlights.map((flight) => <button className={`flight-card ${trip.selectedFlightId === flight.id ? 'is-selected' : ''}`} key={flight.id} onClick={() => update({ selectedFlightId: trip.selectedFlightId === flight.id ? null : flight.id })}><div className="offer-top"><span className="status-badge">{flight.tag}</span><div><strong>{flight.price.toLocaleString()}원</strong><small>1인당</small></div></div><div className="airline"><span>{flight.airline.slice(0, 1)}</span><strong>{flight.airline}</strong><small>{flight.code}</small></div><div className="flight-leg"><strong>{flight.outbound.split(' → ')[0]}</strong><div><span>{flight.duration}</span><i /><small>직항</small></div><strong>{flight.outbound.split(' → ')[1]}</strong></div><div className="flight-leg"><strong>{flight.inbound.split(' → ')[0]}</strong><div><span>{flight.duration}</span><i /><small>직항</small></div><strong>{flight.inbound.split(' → ')[1]}</strong></div><div className="offer-note"><Sparkles size={13} />{flight.note}</div><span className={`select-indicator ${trip.selectedFlightId === flight.id ? 'is-selected' : ''}`}>{trip.selectedFlightId === flight.id ? <><Check size={14} /> 선택됨</> : '선택'}</span></button>)}</div><button className="button button--secondary" onClick={() => setPhase('survey')}>조건 다시 설정</button></div>;
}

function StaysStep({ trip, update }: { trip: Trip; update: (patch: Partial<Trip>) => void }) {
  const [phase, setPhase] = useState<'survey' | 'searching' | 'results'>(trip.selectedStayId ? 'results' : 'survey');
  const selectedStay = STAYS.find((stay) => stay.id === trip.selectedStayId);
  useEffect(() => { if (phase === 'searching') { const timer = window.setTimeout(() => setPhase('results'), 2200); return () => window.clearTimeout(timer); } }, [phase]);
  if (phase === 'searching') return <div className="stream-page"><PageHeading eyebrow="AGENT · STAY SEARCH" title="숙소 위치와 가격을 비교하고 있어요" description="일정에 편리한 동네와 이동 시간을 함께 계산합니다." /><AgentPanel type="숙소" progress={68} /><SkeletonCards count={3} /></div>;
  if (phase === 'survey') return <div className="form-page"><PageHeading eyebrow="STEP 4 · 숙소" title="숙소를 찾기 전에" description="위치와 예산만 정해도 충분해요." /><div className="route-summary"><BedDouble size={20} /><div><strong>도쿄 · {trip.startDate} 체크인</strong><span>{getNights(trip.startDate, trip.endDate)}박 · 성인 {trip.persona.adults}명 · 객실 1개</span></div><button>수정</button></div><div className="survey-fields"><Question title="어떤 숙소를 찾으세요?" meta="전체"><div className="interest-list"><button className="is-selected">호텔 <Check size={13} /></button><button>아파트·민박</button><button>호스텔</button><button>료칸</button></div></Question><Question title="위치는 뭐가 중요해요?" meta="최대 2개"><div className="interest-list"><button className="is-selected">도심 한가운데</button><button className="is-selected">역에서 가까운 곳</button><button>관광지 근처</button><button>조용한 동네</button></div></Question><Question title="1박 예산"><input className="range" type="range" min="70000" max="480000" defaultValue="220000" /><div className="range-labels"><span>7만원</span><strong>8만 – 22만원</strong><span>48만원</span></div></Question><Question title="최소 평점"><div className="segmented"><button>무관</button><button>7.0+</button><button className="is-active">8.0+</button><button>9.0+</button></div></Question></div><button className="button button--primary button--wide" onClick={() => setPhase('searching')}><Sparkles size={16} /> 숙소 찾기</button></div>;
  return <div className="split-page"><section className="split-list"><div className="agent-summary"><Sparkles size={15} /><strong>18곳을 찾았어요.</strong><span>위치와 가격의 균형이 좋은 숙소를 먼저 보여드려요.</span></div><div className="results-toolbar"><div><button className="button button--secondary button--small">필터 (2)</button><button className="button button--ghost button--small">추천순 <ChevronDown size={14} /></button></div><span>18곳</span></div><div className="stay-list">{STAYS.map((stay) => <button className={`stay-card ${trip.selectedStayId === stay.id ? 'is-selected' : ''}`} key={stay.id} onClick={() => update({ selectedStayId: trip.selectedStayId === stay.id ? null : stay.id })}><div className="stay-card__image" style={{ backgroundImage: `url(${stay.image})` }}><span>1/6</span></div><div className="stay-card__body"><span className="status-badge">{stay.tag}</span><h3>{stay.name}</h3><p>★★★★ 호텔 · {stay.area}</p><div className="stay-rating"><i /> <strong>{stay.rating}</strong> 훌륭해요 <span>({stay.reviews.toLocaleString()})</span></div><small><TrainFront size={13} />{stay.station}</small><em>무료 취소 가능</em><div className="stay-price"><strong>{stay.price.toLocaleString()}원</strong><span>/1박 · 총 {stay.total.toLocaleString()}원</span></div></div></button>)}</div></section><aside className="split-map"><MapPanel selectedIds={trip.selectedPlaceIds} stay={selectedStay ?? STAYS[0]} /></aside></div>;
}

function PlacesStep({ trip }: { trip: Trip }) {
  const togglePlace = useTripStore((state) => state.togglePlace);
  const [category, setCategory] = useState('전체');
  const [search, setSearch] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);
  const filtered = PLACES.filter((place) => (category === '전체' || place.category === category) && place.name.includes(search));
  const categories = ['전체', ...Array.from(new Set(PLACES.map((place) => place.category)))];
  return <div className="split-page"><section className="split-list"><div className="agent-summary"><Sparkles size={15} /><strong>도쿄에서 {PLACES.length}곳을 찾았어요.</strong><span>관심사에 맞는 곳을 위로 올려뒀습니다.</span></div><div className="place-controls"><div className="input-with-icon"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="장소 검색" /></div><div className="category-tabs">{categories.map((item) => <button className={category === item ? 'is-active' : ''} key={item} onClick={() => setCategory(item)}>{item} <span>{item === '전체' ? PLACES.length : PLACES.filter((place) => place.category === item).length}</span></button>)}</div><button className="button button--secondary button--small"><Link2 size={14} /> 링크로 추가</button></div><div className="place-list">{filtered.map((place) => { const selected = trip.selectedPlaceIds.includes(place.id); return <article className={`place-card ${selected ? 'is-selected' : ''} ${activeId === place.id ? 'is-active' : ''}`} key={place.id} onMouseEnter={() => setActiveId(place.id)} onMouseLeave={() => setActiveId(null)}><button className="place-card__select" onClick={() => togglePlace(trip.id, place.id)} aria-label={`${place.name} 선택`}>{selected && <Check size={13} />}</button><button className="place-card__detail" onClick={() => setActiveId(place.id)}><div className="place-image" style={{ backgroundImage: `url(${place.image})` }} /><div><div className="place-card__title"><h3>{place.name}</h3>{place.closed && <span className="danger-badge">{place.closed}</span>}</div><p>{place.category} · {place.area}</p><div className="place-rating"><Star size={13} />{place.rating} <span>({place.reviews.toLocaleString()})</span> · <Clock3 size={13} /> {Math.floor(place.duration / 60) ? `${Math.floor(place.duration / 60)}시간 ` : ''}{place.duration % 60 || ''}{place.duration % 60 ? '분' : ''}</div><small>{place.summary}</small><div className="place-tags"><span>{place.price}</span>{place.reservation && <span className="warning-badge">예약 권장</span>}<em><Sparkles size={12} />{place.note}</em></div></div></button></article>; })}</div><div className="selection-summary"><strong><Check size={15} /> {trip.selectedPlaceIds.length}곳 선택</strong><span>예상 소요 {Math.round(trip.selectedPlaceIds.reduce((sum, id) => sum + (PLACES.find((place) => place.id === id)?.duration ?? 0), 0) / 60)}시간</span><span>하루 평균 {(trip.selectedPlaceIds.length / Math.max(1, getNights(trip.startDate, trip.endDate) + 1)).toFixed(1)}곳</span></div></section><aside className="split-map"><MapPanel selectedIds={trip.selectedPlaceIds} activeId={activeId} onMarkerClick={setActiveId} stay={STAYS.find((stay) => stay.id === trip.selectedStayId) ?? null} /></aside></div>;
}

function ItineraryStep({ trip }: { trip: Trip }) {
  const generate = useTripStore((state) => state.generateItinerary);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [tab, setTab] = useState<'schedule' | 'expense' | 'checklist'>('schedule');
  if (!trip.itinerary) return <div className="generation-page"><PageHeading eyebrow="STEP 6 · 일정 생성" title="선택한 장소로 일정을 설계할게요" description={`${trip.selectedPlaceIds.length}곳의 위치와 영업시간, 이동 동선을 함께 고려합니다.`} /><div className="generation-visual"><div className="generation-orbit"><WandSparkles size={28} /></div><div><span><CheckCircle2 size={15} /> 장소를 지역별로 묶기</span><span><CheckCircle2 size={15} /> 영업시간과 휴관일 확인</span><span><Circle size={15} /> 이동 시간 계산</span><span><Circle size={15} /> 일자별 일정 배치</span></div></div><button className="button button--primary button--large" onClick={() => generate(trip.id)}><Sparkles size={17} /> AI로 일정 만들기</button></div>;
  const allPlaceIds = trip.itinerary.flatMap((day) => day.items.map((item) => item.placeId).filter((id): id is string => Boolean(id)));
  return <div className="split-page itinerary-page"><section className="split-list"><div className="agent-summary"><Sparkles size={15} /><strong>{trip.itinerary.length}일 일정을 완성했어요.</strong><span>같은 지역을 묶어 이동을 줄였습니다.</span></div><div className="itinerary-toolbar"><div className="tabs"><button className={tab === 'schedule' ? 'is-active' : ''} onClick={() => setTab('schedule')}>일정</button><button className={tab === 'expense' ? 'is-active' : ''} onClick={() => setTab('expense')}>지출</button><button className={tab === 'checklist' ? 'is-active' : ''} onClick={() => setTab('checklist')}>준비물</button></div><button className="button button--secondary button--small"><WandSparkles size={14} /> 경로 최적화</button></div>{tab === 'schedule' && <div className="day-list">{trip.itinerary.map((day, dayIndex) => <section className="day-section" key={day.id}><header><ChevronDown size={16} /><i style={{ background: `var(--day-${(dayIndex % 6) + 1})` }} /><div><div><strong>Day {dayIndex + 1}</strong><span>{day.date.slice(5)} · {day.title}</span></div><small>{day.items.filter((item) => item.kind === 'place').length}곳 · 활동 {Math.round(day.items.reduce((sum, item) => sum + item.duration, 0) / 60)}시간 · 이동 {day.items.reduce((sum, item) => sum + (item.travelMinutes ?? 0), 0)}분</small></div></header><div className="day-items">{day.items.map((item, itemIndex) => { const place = PLACES.find((value) => value.id === item.placeId); const placeNumber = day.items.slice(0, itemIndex + 1).filter((value) => value.kind === 'place').length; return <div key={item.id}>{<article className={`itinerary-card ${activeId === item.placeId ? 'is-active' : ''}`} onMouseEnter={() => setActiveId(item.placeId ?? null)} onMouseLeave={() => setActiveId(null)}><GripVertical size={15} /><span className={`item-number ${item.kind !== 'place' ? 'is-icon' : ''}`} style={{ background: item.kind === 'place' ? `var(--day-${(dayIndex % 6) + 1})` : undefined }}>{item.kind === 'place' ? placeNumber : item.kind === 'flight' ? <Plane size={12} /> : item.kind === 'stay' ? <BedDouble size={12} /> : <UtensilsCrossed size={12} />}</span><time>{item.time}</time><div className="itinerary-card__body"><strong>{item.title}</strong><span>{place ? `${place.category} · ${Math.floor(item.duration / 60)}시간 ${item.duration % 60 || ''}분` : item.kind === 'flight' ? '항공 이동' : '여행 일정'}</span>{place && <small><Star size={12} /> {place.rating} · {place.price}</small>}</div>{place?.closed ? <TriangleAlert className="warning-icon" size={15} /> : <CheckCircle2 className="success-icon" size={15} />}</article>}{itemIndex < day.items.length - 1 && <div className="travel-connector"><span /><Footprints size={13} /><strong>{item.travelMinutes ?? 12}분</strong><em>{item.travelMode}</em></div>}</div>; })}</div><button className="add-place-button"><Plus size={14} /> 장소 추가</button></section>)}</div>}{tab === 'expense' && <ExpensePanel trip={trip} />}{tab === 'checklist' && <ChecklistPanel />}</section><aside className="split-map"><MapPanel selectedIds={allPlaceIds} activeId={activeId} onMarkerClick={setActiveId} showRoute stay={STAYS.find((stay) => stay.id === trip.selectedStayId) ?? null} /></aside></div>;
}

function ExpensePanel({ trip }: { trip: Trip }) {
  const flight = FLIGHTS.find((item) => item.id === trip.selectedFlightId)?.price ?? 0;
  const stay = STAYS.find((item) => item.id === trip.selectedStayId)?.total ?? 0;
  const activities = trip.selectedPlaceIds.length * 22000;
  const total = flight + stay + activities + 152000;
  return <div className="expense-panel"><header><div><span>예상 지출</span><strong>{total.toLocaleString()}원</strong></div><div className="budget-bar"><span style={{ width: `${Math.min(100, (total / 1600000) * 100)}%` }} /></div><small>예산 1,600,000원 중 {Math.round((total / 1600000) * 100)}% 사용</small></header>{[['항공권', flight], ['숙소', stay], ['입장료 · 활동', activities], ['식사 (추정)', 120000], ['교통 (추정)', 32000]].map(([label, amount]) => <div key={String(label)}><span>{label}</span><strong>{Number(amount).toLocaleString()}원</strong></div>)}</div>;
}

function ChecklistPanel() {
  return <div className="checklist-panel"><h3>예약 필요</h3>{['팀랩 플래닛 사전 예약', '시부야 스카이 입장 시간 예약'].map((item, index) => <label key={item}><input type="checkbox" defaultChecked={index === 0} /><span>{item}</span><small>Day {index + 2}</small></label>)}<h3>날씨 대비</h3><label><input type="checkbox" /><span>접이식 우산 준비</span><small>여행 기간 중 비 예보 가능</small></label><button><Plus size={14} /> 항목 추가</button></div>;
}

function VerifyStep({ trip }: { trip: Trip }) {
  const verify = useTripStore((state) => state.verifyItinerary);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    if (!running) return;
    let nextProgress = 0;
    const timer = window.setInterval(() => {
      nextProgress += 1;
      setProgress(nextProgress);
      if (nextProgress >= 10) {
        window.clearInterval(timer);
        setRunning(false);
        verify(trip.id);
      }
    }, 280);
    return () => window.clearInterval(timer);
  }, [running, trip.id, verify]);
  if (!trip.verification && !running) return <div className="verify-intro"><div className="verify-shield"><ShieldCheck size={36} /></div><PageHeading eyebrow="STEP 7 · 최종 점검" title="일정을 검증할게요" description="휴관일, 이동 시간, 예산, 접근성 등 10가지를 확인합니다." /><div className="verify-intro__summary"><span><CalendarDays size={16} />{trip.itinerary?.length ?? 0}일 일정</span><span><MapPin size={16} />방문지 {trip.selectedPlaceIds.length}곳</span><span><ListChecks size={16} />검사 항목 10개</span></div><button className="button button--primary button--large" onClick={() => { setProgress(0); setRunning(true); }}><ShieldCheck size={17} /> 검증 시작</button></div>;
  if (running) return <div className="verify-running"><section><div className="verify-running__header"><div><h1>일정을 검증하고 있어요</h1><span>{progress}/10</span></div><div className="verification-progress"><span style={{ width: `${progress * 10}%` }} /></div></div><div className="verify-checklist">{['영업시간 · 휴관일', '이동 시간 실현성', '항공 도착 · 출발 여유', '숙소 체크인 · 체크아웃', '하루 일정량', '예산', '접근성', '관심사 반영', '사전 예약 필요', '시즌 · 날씨'].map((label, index) => <div className={index === progress ? 'is-running' : ''} key={label}>{index < progress ? <CheckCircle2 size={16} /> : index === progress ? <Loader2 className="spin" size={16} /> : <Circle size={16} />}<strong>{label}</strong><span>{index < progress ? (index === 0 ? '충돌 1' : index === 1 || index === 4 ? '주의 1' : '정상') : index === progress ? '검사 중…' : '대기'}</span></div>)}</div></section><ReasoningConsole progress={progress} /></div>;
  const checks = trip.verification ?? [];
  const pass = checks.filter((check) => check.status === 'pass').length;
  const warnings = checks.filter((check) => check.status === 'warning').length;
  const conflicts = checks.filter((check) => check.status === 'conflict').length;
  return <div className="verify-report"><section className="score-card"><div><span className="eyebrow">VERIFICATION COMPLETE</span><h1>검증을 마쳤어요</h1><p>충돌 {conflicts}건을 해결하면 일정이 완성돼요.</p></div><div className="score-counts"><span className="pass"><strong>{pass}</strong>정상</span><span className="warning"><strong>{warnings}</strong>주의</span><span className="conflict"><strong>{conflicts}</strong>충돌</span></div></section><div className="report-heading"><h2>해결해야 할 것</h2><button className="button button--primary button--small"><WandSparkles size={14} /> 자동 수정 모두 적용</button></div><div className="issue-list">{checks.filter((check) => check.status === 'warning' || check.status === 'conflict').map((check, index) => <article className={`issue-card is-${check.status}`} key={check.id}><header><span>{check.status === 'conflict' ? <CircleX size={14} /> : <TriangleAlert size={14} />}{check.status === 'conflict' ? '충돌' : '주의'}</span><code>[{check.id}]</code></header><h3>{check.message}</h3><p>{index === 0 ? '도쿄 국립박물관은 매주 월요일 휴관입니다. 같은 지역을 방문하는 다른 날로 옮기는 것이 좋아요.' : '현재 일정과 여행 페이스를 비교해 조정이 필요한 항목입니다.'}</p><div className="evidence"><strong>근거</strong><span>· 장소 운영 정보와 방문 예정 시간을 대조했습니다.</span><span>· 현재 이동 경로와 체류 시간을 함께 계산했습니다.</span></div><div className="fix-suggestion"><Sparkles size={14} /><div><strong>제안</strong><span>{index === 0 ? 'Day 3 오전으로 옮기면 같은 우에노 권역에서 이동할 수 있어요.' : '마지막 방문지를 다음 날로 옮겨 여유를 확보해요.'}</span><small>예상 이동 시간 +4분</small></div></div><footer><button className="button button--secondary button--small">일정에서 보기</button><button className="button button--ghost button--small">무시하기</button><button className="button button--primary button--small">이 수정 적용</button></footer></article>)}</div><details className="passed-checks"><summary><CheckCircle2 size={16} /> 통과한 항목 {pass}개 <ChevronDown size={15} /></summary>{checks.filter((check) => check.status === 'pass').map((check) => <div key={check.id}><Check size={14} /><strong>{check.label}</strong><span>{check.message}</span></div>)}</details></div>;
}

function ReasoningConsole({ progress }: { progress: number }) {
  const labels = ['영업시간 · 휴관일', '이동 시간 실현성', '항공 도착 · 출발 여유', '숙소 체크인 · 체크아웃', '하루 일정량', '예산', '접근성', '관심사 반영', '사전 예약 필요', '시즌 · 날씨'];
  return <aside className="reasoning-console"><header><span><Sparkles size={15} /> 추론 과정</span><button>중단</button></header><div><p>여행 일정의 방문지와 이동 구간을 10개 항목으로 점검합니다.</p>{labels.slice(0, Math.max(1, progress + 1)).map((label, index) => <section key={label}><strong>[V{index + 1}] {label}</strong><code>&gt; 관련 일정과 장소 데이터 조회</code><code>&gt; Day별 방문 시각 및 이동 경로 계산</code>{index < progress && <em>{index === 0 ? '✕ 월요일 휴관 장소 1곳 발견' : index === 1 || index === 4 ? '△ 일정 여유 확인 필요' : '→ 문제 없음'}</em>}</section>)}<span className="console-cursor" /></div></aside>;
}

function SkeletonCards({ count }: { count: number }) {
  return <div className="skeleton-list">{Array.from({ length: count }, (_, index) => <div className="result-skeleton" key={index}><span /><div><i /><i /><i /></div><em /></div>)}</div>;
}

function getNights(start: string, end: string) {
  if (!start || !end) return 0;
  return Math.max(0, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86400000));
}
