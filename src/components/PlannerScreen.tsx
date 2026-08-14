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
  MapPinned,
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
  Trash2,
  Trees,
  TriangleAlert,
  User,
  Users,
  UtensilsCrossed,
  WandSparkles,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { AgentPanel } from '@/components/AgentPanel';
import { AppShell } from '@/components/AppShell';
import { MapPanel } from '@/components/MapPanel';
import { PlaceDetailModal } from '@/components/PlaceDetailModal';
import type { PlaceDetail } from '@/components/PlaceDetailModal';
import { CITIES, FLIGHTS, INTERESTS, ORIGIN_CITIES, PLACES, STAYS } from '@/lib/data';
import { isVerificationCurrent } from '@/lib/itinerary';
import { createManualUrlPlace, parseGoogleMapsUrl, parsePlaceFile } from '@/lib/placeImport';
import { getTripPlace, getTripPlaces, isImportedPlace } from '@/lib/places';
import { useTripStore } from '@/lib/store';
import type { ImportedPlace, ItineraryDay, StepId, Trip, TripPlace, VerificationCheck } from '@/lib/types';
import messages from '../../messages/ko.json';

const STEP_ORDER: StepId[] = ['city', 'persona', 'flights', 'stays', 'places', 'itinerary', 'verify'];
const STEP_LABELS: Record<StepId, string> = {
  city: '도시', persona: '여행 스타일', flights: '항공권', stays: '숙소', places: '가고 싶은 곳', itinerary: '일정', verify: '검증',
};

const formatDurationLabel = (duration: number) => {
  const hours = Math.floor(duration / 60);
  const minutes = duration % 60;
  if (hours === 0) return `${minutes}분`;
  return `${hours}시간${minutes ? ` ${minutes}분` : ''}`;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const readAgentPlan = (payload: unknown): { itinerary: ItineraryDay[]; verification: VerificationCheck[] | null } | null => {
  if (Array.isArray(payload)) return { itinerary: payload as ItineraryDay[], verification: null };
  if (!isRecord(payload) || !Array.isArray(payload.itinerary)) return null;
  return {
    itinerary: payload.itinerary as ItineraryDay[],
    verification: Array.isArray(payload.verification) ? payload.verification as VerificationCheck[] : null,
  };
};

const readAgentVerification = (payload: unknown): VerificationCheck[] | null => {
  if (Array.isArray(payload)) return payload as VerificationCheck[];
  return isRecord(payload) && Array.isArray(payload.verification) ? payload.verification as VerificationCheck[] : null;
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
  const hasHydrated = useTripStore((state) => state.hasHydrated);
  const ensureTrip = useTripStore((state) => state.ensureTrip);
  const completeStep = useTripStore((state) => state.completeStep);
  const updateTrip = useTripStore((state) => state.updateTrip);
  const saveItinerary = useTripStore((state) => state.saveItinerary);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (hasHydrated) ensureTrip(tripId);
  }, [ensureTrip, hasHydrated, tripId]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 2600);
    return () => window.clearTimeout(timer);
  }, [notice]);

  if (!hasHydrated || !trip) return <div className="page-loading"><Loader2 className="spin" size={24} /><span>여행을 불러오고 있어요</span></div>;

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
    if (step === 'flights' && trip.persona.includeFlights === true) {
      const selectedOffer = FLIGHTS.find((flight) => flight.id === trip.selectedFlightId);
      const selectedOfferMatchesRoute = selectedOffer?.originId === trip.originId && selectedOffer.destinationId === trip.destinationId;
      if (!selectedOfferMatchesRoute) {
        const routeHasOffers = FLIGHTS.some((flight) => flight.originId === trip.originId && flight.destinationId === trip.destinationId);
        return setNotice(routeHasOffers
          ? '현재 검색 조건의 항공권을 선택해야 다음 단계로 이동할 수 있어요'
          : '현재 노선은 데모 항공편이 없어 항공권 선택을 완료할 수 없어요');
      }
    }
    if (step === 'stays' && trip.persona.includeStays === true && !STAYS.some((stay) => stay.id === trip.selectedStayId)) return setNotice('현재 검색 조건의 숙소를 선택해야 다음 단계로 이동할 수 있어요');
    if (step === 'places' && trip.selectedPlaceIds.length === 0) return setNotice('가고 싶은 곳을 1곳 이상 선택해 주세요');
    if (step === 'itinerary' && !trip.itinerary) return setNotice('일정을 먼저 생성해 주세요');
    if (step === 'verify') {
      if (!isVerificationCurrent(trip)) return setNotice('최신 일정 검증을 완료한 뒤 저장해 주세요');
      setIsSaving(true);
      const saved = saveItinerary(tripId);
      setIsSaving(false);
      if (!saved) return setNotice('일정을 저장하지 못했어요. 다시 시도해 주세요');
      router.push(`/trip/${tripId}`);
      return;
    }
    if (next) {
      completeStep(tripId, step, next);
      router.push(`/plan/${tripId}/${next}`);
    }
  };

  const skip = () => {
    if (step !== 'flights' && step !== 'stays') return;
    if ((step === 'flights' && trip.persona.includeFlights === true) || (step === 'stays' && trip.persona.includeStays === true)) return;
    const skipNext: StepId = step === 'flights' && trip.persona.includeStays ? 'stays' : 'places';
    updateTrip(tripId, step === 'flights' ? { selectedFlightId: 'skipped' } : { selectedStayId: 'skipped' });
    completeStep(tripId, step, skipNext);
    router.push(`/plan/${tripId}/${skipNext}`);
  };

  const footer = (
    <div className="step-footer__inner">
      <div>{previous && <button className="button button--secondary" onClick={() => router.push(`/plan/${tripId}/${previous}`)}><ArrowLeft size={16} /> 이전</button>}</div>
      <div className="footer-actions">
        {((step === 'flights' && trip.persona.includeFlights !== true) || (step === 'stays' && trip.persona.includeStays !== true)) && <button className="button button--ghost" onClick={skip}>이 단계 건너뛰기</button>}
        <button className="button button--primary" onClick={goNext} disabled={isSaving}>
          {step === 'verify' ? (isSaving ? '일정을 저장하고 있어요…' : '일정 저장하기') : `다음: ${next ? STEP_LABELS[next] : ''}`}<ArrowRight size={16} />
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
  const startDateRef = useRef<HTMLInputElement>(null);
  const endDateRef = useRef<HTMLInputElement>(null);
  const [originQuery, setOriginQuery] = useState('');
  const [destinationQuery, setDestinationQuery] = useState('');
  const [originMenuOpen, setOriginMenuOpen] = useState(!trip.originId);
  const [destinationMenuOpen, setDestinationMenuOpen] = useState(!trip.destinationId);
  const origin = ORIGIN_CITIES.find((item) => item.id === trip.originId);
  const city = CITIES.find((item) => item.id === trip.destinationId);
  const filteredOrigins = ORIGIN_CITIES.filter((item) => `${item.name} ${item.nameEn} ${item.airportCodes.join(' ')}`.toLowerCase().includes(originQuery.toLowerCase()));
  const filteredDestinations = CITIES.filter((item) => `${item.name} ${item.nameEn} ${item.country} ${item.airportCodes.join(' ')}`.toLowerCase().includes(destinationQuery.toLowerCase()));
  const routeReady = Boolean(origin && city);
  const openDatePicker = (input: HTMLInputElement | null, disabled: boolean) => {
    if (!input || disabled) return;
    input.focus();
    try {
      input.showPicker?.();
    } catch {
      // Focus remains as a fallback where browsers restrict showPicker().
    }
  };

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
    update({ destinationId: id, title: `${selected?.name ?? '새'} 여행`, selectedFlightId: null, selectedStayId: null, selectedPlaceIds: [], placeDurations: {}, importedPlaces: {}, itinerary: null, verification: null });
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
            {(!originQuery || filteredOrigins.length > 0) && <div className="city-options">
              <span className="option-group">{originQuery ? '검색 결과' : '출발 도시'}</span>
              {filteredOrigins.map((item, index) => <button key={item.id} className={index === 0 ? 'is-active' : ''} onClick={() => selectOrigin(item.id)}><span>{item.flag}</span><strong>{item.name}</strong><small>{item.airportCodes.join(' · ')}</small><em>데모 데이터</em></button>)}
            </div>}
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
            {(!destinationQuery || filteredDestinations.length > 0) && <div className="city-options">
              <span className="option-group">{destinationQuery ? '검색 결과' : '인기 도시'}</span>
              {filteredDestinations.map((item, index) => <button key={item.id} className={index === 0 ? 'is-active' : ''} onClick={() => selectDestination(item.id)}><span>{item.flag}</span><strong>{item.name}</strong><small>{item.country} · {item.nameEn}</small><em>데모 데이터</em></button>)}
            </div>}
          </div>
        )}
      </section>
      <section className={`form-section ${!routeReady ? 'is-disabled' : ''}`}>
        <div className="field-label"><span>{messages.city.date}</span>{trip.startDate && trip.endDate && <em>{getNights(trip.startDate, trip.endDate)}박 {getNights(trip.startDate, trip.endDate) + 1}일</em>}</div>
        <div className="date-card">
          <div className="date-field" onClick={(event) => { if (event.target === startDateRef.current) return; event.preventDefault(); openDatePicker(startDateRef.current, !routeReady); }}><CalendarDays size={18} /><label>가는 날<input ref={startDateRef} type="date" disabled={!routeReady} value={trip.startDate} min={new Date().toISOString().slice(0, 10)} onClick={() => openDatePicker(startDateRef.current, !routeReady)} onChange={(event) => update({ startDate: event.target.value, endDate: trip.endDate && trip.endDate < event.target.value ? '' : trip.endDate })} /></label></div>
          <ArrowRight size={16} />
          <div className="date-field" onClick={(event) => { if (event.target === endDateRef.current) return; event.preventDefault(); openDatePicker(endDateRef.current, !routeReady || !trip.startDate); }}><CalendarDays size={18} /><label>돌아오는 날<input ref={endDateRef} type="date" disabled={!routeReady || !trip.startDate} value={trip.endDate} min={trip.startDate} onClick={() => openDatePicker(endDateRef.current, !routeReady || !trip.startDate)} onChange={(event) => update({ endDate: event.target.value })} /></label></div>
        </div>
        {trip.startDate && trip.endDate ? <div className="date-summary"><CheckCircle2 size={16} /><div><strong>{trip.startDate} → {trip.endDate}</strong><span>{getNights(trip.startDate, trip.endDate)}박 {getNights(trip.startDate, trip.endDate) + 1}일 여행</span></div></div> : <p className="field-hint">{routeReady ? messages.city.chooseDate : '출발지와 목적지를 먼저 선택해 주세요'}</p>}
      </section>
    </div>
  );
}

function PersonaStep({ trip, update }: { trip: Trip; update: (patch: Partial<Trip>) => void }) {
  const persona = trip.persona;
  const stayQuestionRef = useRef<HTMLDivElement>(null);
  const companionSectionRef = useRef<HTMLElement>(null);
  const preferenceQuestionsRef = useRef<HTMLDivElement>(null);
  const interestsQuestionRef = useRef<HTMLDivElement>(null);
  const [paceConfirmed, setPaceConfirmed] = useState(persona.interests.length > 0);
  const [pendingScroll, setPendingScroll] = useState<'stay' | 'companion' | 'preferences' | 'interests' | null>(null);
  const showStayQuestion = persona.includeFlights !== null;
  const showCompanionQuestion = persona.includeStays !== null;
  const showPreferenceQuestions = Boolean(persona.companion);
  const showInterests = paceConfirmed || persona.interests.length > 0;
  const isSolo = persona.companion === 'solo';
  const requiredDone = [persona.includeFlights !== null, persona.includeStays !== null, Boolean(persona.companion), persona.interests.length > 0].filter(Boolean).length;
  const patchPersona = (patch: Partial<Trip['persona']>) => update({ persona: { ...persona, ...patch } });
  const transportModes = persona.preferredTransportModes ?? [];
  const toggleTransport = (mode: 'walking' | 'publicTransit') => patchPersona({
    preferredTransportModes: transportModes.includes(mode)
      ? transportModes.filter((item) => item !== mode)
      : [...transportModes, mode],
  });
  const companions = [{ id: 'solo', label: '혼자', icon: User }, { id: 'couple', label: '연인', icon: Heart }, { id: 'family', label: '가족', icon: Users }, { id: 'friends', label: '친구', icon: Users }, { id: 'work', label: '동료', icon: BriefcaseBusiness }];
  useEffect(() => {
    if (!pendingScroll) return;
    const frame = window.requestAnimationFrame(() => {
      const target = pendingScroll === 'stay'
        ? stayQuestionRef.current
        : pendingScroll === 'companion'
          ? companionSectionRef.current
          : pendingScroll === 'preferences'
            ? preferenceQuestionsRef.current
            : interestsQuestionRef.current;
      if (!target) return;
      target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
      setPendingScroll(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pendingScroll]);
  const selectFlightPreference = (includeFlights: boolean) => {
    patchPersona({ includeFlights });
    setPendingScroll('stay');
  };
  const selectStayPreference = (includeStays: boolean) => {
    patchPersona({ includeStays });
    setPendingScroll('companion');
  };
  const selectCompanion = (companion: string) => {
    patchPersona(companion === 'solo' ? { companion, adults: 1 } : { companion });
    setPendingScroll('preferences');
  };
  const selectPace = (pace: Trip['persona']['pace']) => {
    patchPersona({ pace });
    setPaceConfirmed(true);
    setPendingScroll('interests');
  };
  return (
    <div className="form-page">
      <PageHeading eyebrow="STEP 2 · 취향 설정" title={messages.persona.title} description={messages.persona.description} />
      <div className="persona-progress"><div><span style={{ width: `${requiredDone * 25}%` }} /></div><strong>필수 4개 중 {requiredDone}개 완료</strong></div>
      <section className="persona-section"><div className="section-divider"><span>함께 찾을 것</span></div><Question title="항공권을 함께 찾아드릴까요?" done={persona.includeFlights !== null}><div className="choice-grid choice-grid--two"><ChoiceCard selected={persona.includeFlights === true} onClick={() => selectFlightPreference(true)} icon={<Plane />} title="네, 찾아주세요" description="조건에 맞는 왕복 항공권을 비교해요" /><ChoiceCard selected={persona.includeFlights === false} onClick={() => selectFlightPreference(false)} icon={<CircleX />} title="아니요, 괜찮아요" description="이미 예약했거나 직접 알아볼게요" /></div></Question>{showStayQuestion && <div ref={stayQuestionRef} className="progressive-reveal"><Question title="숙소를 함께 찾아드릴까요?" done={persona.includeStays !== null}><div className="choice-grid choice-grid--two"><ChoiceCard selected={persona.includeStays === true} onClick={() => selectStayPreference(true)} icon={<Hotel />} title="네, 찾아주세요" description="위치와 예산을 비교해 추천해요" /><ChoiceCard selected={persona.includeStays === false} onClick={() => selectStayPreference(false)} icon={<CircleX />} title="아니요, 괜찮아요" description="이미 정한 숙소를 기준으로 계획해요" /></div></Question></div>}</section>
      {showCompanionQuestion && (
        <section ref={companionSectionRef} className="persona-section progressive-reveal">
          <div className="section-divider"><span>누구와, 어떻게</span></div>
          <Question title="누구와 함께 가세요?" done={Boolean(persona.companion)}>
            <div className="choice-grid choice-grid--five">{companions.map(({ id, label, icon: Icon }) => <button type="button" key={id} className={`compact-choice ${persona.companion === id ? 'is-selected' : ''}`} onClick={() => selectCompanion(id)}><Icon size={19} /><span>{label}</span>{persona.companion === id && <Check size={13} />}</button>)}</div>
          </Question>
          {showPreferenceQuestions && (
            <div ref={preferenceQuestionsRef} className="progressive-reveal">
              <Question title="동행하는 사람을 자연어로 알려주세요" done={Boolean(persona.companionDescription?.trim())} meta="선택">
                <label className="companion-description"><span>관계, 성향, 필요한 배려를 자유롭게 적어주세요</span><textarea value={persona.companionDescription ?? ''} onChange={(event) => patchPersona({ companionDescription: event.target.value })} placeholder="예: 부모님과 함께 가요. 오래 걷기 어려워하시고 조용한 식당을 좋아하세요." maxLength={500} /><small>데모에서는 여행 메모로 저장되며 AI 연결 시 일정 생성에 반영돼요 · {persona.companionDescription?.length ?? 0}/500</small></label>
              </Question>
              <Question title="인원은 몇 명인가요?" done>
                <div className="counter-row"><div><strong>성인</strong><span>13세 이상</span></div><div><button type="button" aria-label="성인 인원 줄이기" disabled={isSolo} onClick={() => patchPersona({ adults: Math.max(1, persona.adults - 1) })}><Minus size={14} /></button><strong>{isSolo ? 1 : persona.adults}</strong><button type="button" aria-label="성인 인원 늘리기" disabled={isSolo} onClick={() => patchPersona({ adults: Math.min(20, persona.adults + 1) })}><Plus size={14} /></button></div></div>
                {isSolo && <p className="counter-hint">혼자 여행은 성인 1명으로 고정돼요.</p>}
              </Question>
              <Question title="여행 페이스는 어떻게 할까요?" done={paceConfirmed}>
                <div className="choice-grid choice-grid--three">{([['relaxed', '여유롭게', '하루 2–3곳'], ['balanced', '적당히', '하루 3–4곳'], ['packed', '빽빽하게', '하루 5곳 이상']] as const).map(([id, label, detail]) => <button type="button" key={id} className={`pace-card ${persona.pace === id ? 'is-selected' : ''}`} onClick={() => selectPace(id)}><strong>{label}</strong><span>{detail}</span><small>{id === 'relaxed' ? '이동 최소화' : id === 'balanced' ? '균형 잡힌 일정' : '최대한 많이'}</small></button>)}</div>
              </Question>
              {showInterests && <div ref={interestsQuestionRef} className="progressive-reveal"><Question title="어떤 걸 좋아하세요?" done={persona.interests.length > 0} meta={`${persona.interests.length}개 선택`}><div className="interest-list">{INTERESTS.map((interest, index) => { const selected = persona.interests.includes(interest); const icons = [UtensilsCrossed, Coffee, Trees, Landmark, Landmark, ShoppingBag, Star, Navigation, MapPin, Accessibility]; const Icon = icons[index]; return <button type="button" key={interest} className={selected ? 'is-selected' : ''} onClick={() => patchPersona({ interests: selected ? persona.interests.filter((item) => item !== interest) : [...persona.interests, interest] })}><Icon size={15} />{interest}{selected && <Check size={13} />}</button>; })}</div></Question></div>}
            </div>
          )}
        </section>
      )}
      {showInterests && <details className="advanced-section progressive-reveal"><summary><ChevronDown size={16} /><div><strong>더 자세히 알려주기</strong><span>이동 수단 · 고려사항 · 예산 · 메모</span></div><em>선택</em></summary><div className="advanced-content"><label>추가 요청<textarea placeholder="예: 많이 걷지 않으면서 현지 음식을 즐기고 싶어요." /></label><div className="preference-row"><button type="button" className={transportModes.includes('walking') ? 'is-selected' : ''} aria-pressed={transportModes.includes('walking')} onClick={() => toggleTransport('walking')}><Footprints size={16} /> 도보 이동 선호{transportModes.includes('walking') && <Check size={13} />}</button><button type="button" className={transportModes.includes('publicTransit') ? 'is-selected' : ''} aria-pressed={transportModes.includes('publicTransit')} onClick={() => toggleTransport('publicTransit')}><TrainFront size={16} /> 대중교통 선호{transportModes.includes('publicTransit') && <Check size={13} />}</button></div></div></details>}
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
  const [departureWindow, setDepartureWindow] = useState<'night' | 'morning' | 'afternoon' | 'evening'>(() => {
    const selectedDepartureHour = Number(FLIGHTS.find((flight) => flight.id === trip.selectedFlightId)?.outbound.slice(0, 2));
    if (selectedDepartureHour < 6) return 'night';
    if (selectedDepartureHour < 12) return 'morning';
    if (selectedDepartureHour < 18) return 'afternoon';
    return Number.isFinite(selectedDepartureHour) ? 'evening' : 'morning';
  });
  const [sortMode, setSortMode] = useState<'price' | 'duration'>('price');
  const [preferredAirlineCodes, setPreferredAirlineCodes] = useState<string[]>(['KE', 'JL']);
  const airlines = [{ code: 'KE', name: '대한항공' }, { code: 'OZ', name: '아시아나항공' }, { code: 'JL', name: '일본항공' }, { code: 'NH', name: '전일본공수' }];
  const togglePreferredAirline = (code: string) => setPreferredAirlineCodes((current) => current.includes(code) ? current.filter((item) => item !== code) : [...current, code]);
  const origin = ORIGIN_CITIES.find((item) => item.id === trip.originId);
  const destination = CITIES.find((item) => item.id === trip.destinationId);
  const departureWindows = [
    { id: 'night', label: '새벽', range: '00–06', from: 0, to: 6 },
    { id: 'morning', label: '오전', range: '06–12', from: 6, to: 12 },
    { id: 'afternoon', label: '오후', range: '12–18', from: 12, to: 18 },
    { id: 'evening', label: '저녁', range: '18–24', from: 18, to: 24 },
  ] as const;
  const routeFlights = FLIGHTS.filter((flight) => flight.originId === trip.originId && flight.destinationId === trip.destinationId);
  const selectedWindow = departureWindows.find((item) => item.id === departureWindow) ?? departureWindows[1];
  const availableFlights = routeFlights.filter((flight) => {
    const hour = Number(flight.outbound.slice(0, 2));
    return hour >= selectedWindow.from && hour < selectedWindow.to;
  });
  const durationMinutes = (value: string) => {
    const match = value.match(/(?:(\d+)시간)?\s*(?:(\d+)분)?/);
    return Number(match?.[1] ?? 0) * 60 + Number(match?.[2] ?? 0);
  };
  const sortedFlights = [...availableFlights].sort((a, b) => {
    const preferenceDelta = Number(!preferredAirlineCodes.some((code) => a.code.startsWith(code)))
      - Number(!preferredAirlineCodes.some((code) => b.code.startsWith(code)));
    if (preferenceDelta !== 0) return preferenceDelta;
    return sortMode === 'price' ? a.price - b.price : durationMinutes(a.duration) - durationMinutes(b.duration);
  });
  if (phase === 'searching') return <div className="stream-page"><PageHeading eyebrow="AGENT · FLIGHT SEARCH" title="조건에 맞는 항공권을 비교하고 있어요" description="검색 과정과 판단 근거를 실시간으로 보여드릴게요." /><AgentPanel type="항공권" task="flightSearch" input={{ originId: trip.originId, destinationId: trip.destinationId, startDate: trip.startDate, endDate: trip.endDate, persona: trip.persona }} onDone={() => setPhase('results')} onAbort={() => setPhase('survey')} /><SkeletonCards count={3} /></div>;
  if (phase === 'survey') return <div className="form-page"><PageHeading eyebrow="STEP 3 · 항공권" title="항공권을 찾기 전에" description="조건을 알려주시면 맞는 것만 골라드려요. 모두 선택 사항이에요." /><div className="route-summary"><Plane size={20} /><div><strong>{origin?.name ?? '출발지'} ({origin?.airportCodes.join(' · ') ?? '-'}) → {destination?.name ?? '목적지'} ({destination?.airportCodes.join(' · ') ?? '-'})</strong><span>{trip.startDate} 출발 · {trip.endDate} 귀국 · 성인 {trip.persona.adults}명</span></div><button>수정</button></div><div className="survey-fields"><Question title="도착 공항"><div className="interest-list">{destination?.airportCodes.map((code) => <button className="is-selected" key={code}>{destination.name} {code} <Check size={13} /></button>)}</div></Question><Question title="경유"><div className="segmented"><button className="is-active">직항만</button><button>경유도 괜찮아요</button></div></Question><Question title="가는 날 출발 시간대" meta={`${selectedWindow.label} ${selectedWindow.range}`}><div className="flight-time-timeline" role="radiogroup" aria-label="가는 날 출발 시간대">{departureWindows.map((window) => <button type="button" role="radio" aria-checked={departureWindow === window.id} className={departureWindow === window.id ? 'is-selected' : ''} key={window.id} onClick={() => { if (departureWindow !== window.id) update({ selectedFlightId: null, itinerary: null, verification: null }); setDepartureWindow(window.id); }}><span className="timeline-dot" /><strong>{window.label}</strong><small>{window.range}</small></button>)}</div></Question><Question title="선호 항공사" meta={preferredAirlineCodes.length === 0 ? '무관' : `${preferredAirlineCodes.length}개 선택`}><div className="airline-box" role="group" aria-label="선호 항공사 선택">{airlines.map((airline) => { const selected = preferredAirlineCodes.includes(airline.code); return <button type="button" key={airline.code} className={selected ? 'is-selected' : ''} aria-pressed={selected} onClick={() => togglePreferredAirline(airline.code)}><span>{airline.code}</span>{airline.name}{selected && <Check size={14} />}</button>; })}</div><p className="airline-hint">모두 해제하면 항공사 무관으로 검색해요.</p></Question><Question title="1인당 가격 상한"><input className="range" type="range" min="280000" max="950000" defaultValue="900000" /><div className="range-labels"><span>28만원</span><strong>90만원</strong><span>95만원</span></div></Question></div><button className="button button--primary button--wide" onClick={() => setPhase('searching')}><Sparkles size={16} /> 항공권 찾기</button></div>;
  if (availableFlights.length === 0) return <div className="form-page"><PageHeading eyebrow="STEP 3 · 항공권" title={routeFlights.length ? '선택한 시간대의 항공편이 없어요' : '이 노선의 데모 항공편이 아직 없어요'} description={routeFlights.length ? `${selectedWindow.label} ${selectedWindow.range} 출발 조건을 바꿔 다시 찾아보세요.` : `${origin?.name ?? '출발지'}에서 ${destination?.name ?? '목적지'}로 가는 항공편 데이터는 준비 중입니다.`} /><div className="empty-state"><Plane size={36} /><h3>{routeFlights.length ? '다른 출발 시간대를 선택해 주세요' : '항공권을 선택하려면 지원 노선으로 변경해 주세요'}</h3><p>{routeFlights.length ? '검색 조건을 바꾸면 이용 가능한 데모 항공편을 확인할 수 있어요.' : '현재 항공권 데모 데이터는 서울 → 도쿄 노선만 지원하며, 항공권 요청 시 선택 전에는 다음 단계로 진행할 수 없습니다.'}</p><button className="button button--secondary" onClick={() => { update({ selectedFlightId: null, itinerary: null, verification: null }); setPhase('survey'); }}>검색 조건 다시 보기</button></div></div>;
  return <div className="results-page"><div className="agent-summary"><Sparkles size={15} /><strong>{availableFlights.length}개 항공권을 찾았어요.</strong><span>가격과 첫날 활용도를 고려하면 대한항공이 가장 균형이 좋아요.</span><button>추론 보기</button></div><div className="results-toolbar"><div className="segmented" aria-label="항공권 정렬"><button className={sortMode === 'price' ? 'is-active' : ''} onClick={() => setSortMode('price')}>최저가</button><button className={sortMode === 'duration' ? 'is-active' : ''} onClick={() => setSortMode('duration')}>최단시간</button></div><span>{sortedFlights.length}개 표시</span></div><div className="flight-list">{sortedFlights.map((flight) => <button type="button" aria-pressed={trip.selectedFlightId === flight.id} className={`flight-card ${trip.selectedFlightId === flight.id ? 'is-selected' : ''}`} key={flight.id} onClick={() => update({ selectedFlightId: trip.selectedFlightId === flight.id ? null : flight.id, itinerary: null, verification: null })}><div className="offer-top"><span className="status-badge">{flight.tag}</span><div><strong>{flight.price.toLocaleString()}원</strong><small>1인당</small></div></div><div className="airline"><span>{flight.airline.slice(0, 1)}</span><strong>{flight.airline}</strong><small>{flight.code}</small></div><div className="flight-leg"><strong>{flight.outbound.split(' → ')[0]}</strong><div><span>{flight.duration}</span><i /><small>직항</small></div><strong>{flight.outbound.split(' → ')[1]}</strong></div><div className="flight-leg"><strong>{flight.inbound.split(' → ')[0]}</strong><div><span>{flight.duration}</span><i /><small>직항</small></div><strong>{flight.inbound.split(' → ')[1]}</strong></div><div className="offer-note"><Sparkles size={13} />{flight.note}</div></button>)}</div><button className="button button--secondary" onClick={() => { update({ selectedFlightId: null, itinerary: null, verification: null }); setPhase('survey'); }}>조건 다시 설정</button></div>;
}

function StaysStep({ trip, update }: { trip: Trip; update: (patch: Partial<Trip>) => void }) {
  const selectedStay = STAYS.find((stay) => stay.id === trip.selectedStayId);
  const [phase, setPhase] = useState<'survey' | 'searching' | 'results'>(selectedStay ? 'results' : 'survey');
  const [detailPlace, setDetailPlace] = useState<PlaceDetail | null>(null);
  const [selectedTypes, setSelectedTypes] = useState<Array<'hotel' | 'apartment' | 'hostel' | 'ryokan'>>(['hotel']);
  const [priorities, setPriorities] = useState<Array<'central' | 'station' | 'attraction' | 'quiet'>>(['central', 'station']);
  const [maxPrice, setMaxPrice] = useState(Math.max(220000, selectedStay?.price ?? 0));
  const [minRating, setMinRating] = useState(8);
  const typeOptions = [{ id: 'hotel', label: '호텔' }, { id: 'apartment', label: '아파트·민박' }, { id: 'hostel', label: '호스텔' }, { id: 'ryokan', label: '료칸' }] as const;
  const priorityOptions = [{ id: 'central', label: '도심 한가운데' }, { id: 'station', label: '역에서 가까운 곳' }, { id: 'attraction', label: '관광지 근처' }, { id: 'quiet', label: '조용한 동네' }] as const;
  const filteredStays = STAYS.filter((stay) =>
    (selectedTypes.length === 0 || selectedTypes.includes(stay.type)) &&
    (priorities.length === 0 || priorities.some((priority) => stay.features.includes(priority))) &&
    stay.price <= maxPrice && stay.rating >= minRating);

  const clearStaySelection = () => {
    if (trip.selectedStayId) update({ selectedStayId: null, itinerary: null, verification: null });
  };
  const toggleType = (type: typeof typeOptions[number]['id']) => {
    clearStaySelection();
    setSelectedTypes((current) => current.includes(type) ? current.filter((item) => item !== type) : [...current, type]);
  };
  const togglePriority = (priority: typeof priorityOptions[number]['id']) => {
    clearStaySelection();
    setPriorities((current) => {
      if (current.includes(priority)) return current.filter((item) => item !== priority);
      return current.length < 2 ? [...current, priority] : current;
    });
  };
  const changeMaxPrice = (value: number) => {
    clearStaySelection();
    setMaxPrice(value);
  };
  const changeMinRating = (value: number) => {
    clearStaySelection();
    setMinRating(value);
  };
  const openStayDetail = (stay: (typeof STAYS)[number]) => setDetailPlace({
    name: stay.name,
    address: stay.address,
    description: stay.description,
    image: stay.image,
    category: '★★★★ 호텔',
    area: stay.area,
    rating: stay.rating,
    reviewCount: stay.reviews,
    price: `${stay.price.toLocaleString()}원 / 1박`,
    priceDescription: `예상 총액 ${stay.total.toLocaleString()}원`,
    access: stay.station,
    badge: stay.tag,
  });

  if (phase === 'searching') return <div className="stream-page"><PageHeading eyebrow="AGENT · STAY SEARCH" title="숙소 위치와 가격을 비교하고 있어요" description="일정에 편리한 동네와 이동 시간을 함께 계산합니다." /><AgentPanel type="숙소" task="staySearch" input={{ destinationId: trip.destinationId, startDate: trip.startDate, endDate: trip.endDate, persona: trip.persona, selectedPlaceIds: trip.selectedPlaceIds }} onDone={() => setPhase('results')} onAbort={() => setPhase('survey')} /><SkeletonCards count={3} /></div>;
  if (phase === 'survey') return <div className="form-page"><PageHeading eyebrow="STEP 4 · 숙소" title="숙소를 찾기 전에" description="위치와 예산만 정해도 충분해요." /><div className="route-summary"><BedDouble size={20} /><div><strong>도쿄 · {trip.startDate} 체크인</strong><span>{getNights(trip.startDate, trip.endDate)}박 · 성인 {trip.persona.adults}명 · 객실 1개</span></div><button>수정</button></div><div className="survey-fields"><Question title="어떤 숙소를 찾으세요?" meta={selectedTypes.length ? `${selectedTypes.length}개 선택` : '전체'}><div className="interest-list">{typeOptions.map((option) => { const selected = selectedTypes.includes(option.id); return <button type="button" aria-pressed={selected} className={selected ? 'is-selected' : ''} key={option.id} onClick={() => toggleType(option.id)}>{option.label}{selected && <Check size={13} />}</button>; })}</div></Question><Question title="위치는 뭐가 중요해요?" meta={`${priorities.length}/2`}><div className="interest-list">{priorityOptions.map((option) => { const selected = priorities.includes(option.id); return <button type="button" aria-pressed={selected} className={selected ? 'is-selected' : ''} key={option.id} onClick={() => togglePriority(option.id)}>{option.label}{selected && <Check size={13} />}</button>; })}</div></Question><Question title="1박 예산" meta={`${maxPrice.toLocaleString()}원 이하`}><div className="budget-range"><output>{maxPrice.toLocaleString()}원</output><input className="range" type="range" min="70000" max="480000" step="10000" value={maxPrice} onChange={(event) => changeMaxPrice(Number(event.target.value))} /></div><div className="range-labels"><span>7만원</span><strong>현재 {maxPrice.toLocaleString()}원</strong><span>48만원</span></div></Question><Question title="최소 평점"><div className="segmented">{[0, 7, 8, 9].map((rating) => <button type="button" className={minRating === rating ? 'is-active' : ''} aria-pressed={minRating === rating} key={rating} onClick={() => changeMinRating(rating)}>{rating === 0 ? '무관' : `${rating.toFixed(1)}+`}</button>)}</div></Question></div><button className="button button--primary button--wide" onClick={() => setPhase('searching')}><Sparkles size={16} /> 숙소 찾기</button></div>;
  return <div className="split-page"><section className="split-list"><div className="agent-summary"><Sparkles size={15} /><strong>{filteredStays.length}곳을 찾았어요.</strong><span>선택한 위치, 가격, 평점 조건을 모두 반영했습니다.</span></div><div className="results-toolbar"><div><button className="button button--secondary button--small" onClick={() => setPhase('survey')}>필터 ({selectedTypes.length + priorities.length + (minRating > 0 ? 1 : 0)})</button><button className="button button--ghost button--small">추천순 <ChevronDown size={14} /></button></div><span>{filteredStays.length}곳</span></div>{filteredStays.length === 0 ? <div className="empty-state"><BedDouble size={34} /><h3>조건에 맞는 숙소가 없어요</h3><p>예산이나 평점, 위치 조건을 조정해 주세요.</p><button className="button button--secondary" onClick={() => setPhase('survey')}>조건 수정</button></div> : <div className="stay-list">{filteredStays.map((stay) => <article className="stay-card-shell" key={stay.id}><button type="button" aria-pressed={trip.selectedStayId === stay.id} className={`stay-card ${trip.selectedStayId === stay.id ? 'is-selected' : ''}`} key={stay.id} onClick={() => update({ selectedStayId: trip.selectedStayId === stay.id ? null : stay.id, itinerary: null, verification: null })}><div className="stay-card__image" style={{ backgroundImage: `url(${stay.image})` }}><span>1/6</span></div><div className="stay-card__body"><span className="status-badge">{stay.tag}</span><h3>{stay.name}</h3><p>★★★★ 호텔 · {stay.area}</p><div className="stay-rating"><i /> <strong>{stay.rating}</strong> 훌륭해요 <span>({stay.reviews.toLocaleString()})</span></div><small><TrainFront size={13} />{stay.station}</small><em>무료 취소 가능</em><div className="stay-price"><strong>{stay.price.toLocaleString()}원</strong><span>/1박 · 총 {stay.total.toLocaleString()}원</span></div></div></button><button className="stay-detail-action" type="button" onClick={() => openStayDetail(stay)} aria-label={`${stay.name} 상세히 보기`}><MapPinned size={14} /> 상세히 보기</button></article>)}</div>}</section><aside className="split-map"><MapPanel places={getTripPlaces(trip)} selectedIds={trip.selectedPlaceIds} stay={selectedStay ?? filteredStays[0] ?? null} /></aside><PlaceDetailModal place={detailPlace} onClose={() => setDetailPlace(null)} /></div>;
}

type MapLinkRow = {
  id: string;
  url: string;
  name: string;
  area: string;
  latitude: string;
  longitude: string;
  error?: string;
};

function PlacesStep({ trip }: { trip: Trip }) {
  const togglePlace = useTripStore((state) => state.togglePlace);
  const importPlaces = useTripStore((state) => state.importPlaces);
  const addPlaceToItinerary = useTripStore((state) => state.addPlaceToItinerary);
  const removePlaceFromItinerary = useTripStore((state) => state.removePlaceFromItinerary);
  const [category, setCategory] = useState('전체');
  const [search, setSearch] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detailPlace, setDetailPlace] = useState<PlaceDetail | null>(null);
  const [addedPlacesOpen, setAddedPlacesOpen] = useState(false);
  const [itineraryNotice, setItineraryNotice] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<'links' | 'file' | 'demo'>('links');
  const [importError, setImportError] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [previewPlaces, setPreviewPlaces] = useState<TripPlace[]>([]);
  const [previewSource, setPreviewSource] = useState('');
  const [importedIds, setImportedIds] = useState<string[]>([]);
  const [importDurations, setImportDurations] = useState<Record<string, number>>({});
  const [linkRows, setLinkRows] = useState<MapLinkRow[]>([{ id: 'link-1', url: '', name: '', area: '', latitude: '', longitude: '' }]);
  const allPlaces = getTripPlaces(trip);
  const filtered = allPlaces.filter((place) => (category === '전체' || place.category === category) && `${place.name} ${place.area}`.toLowerCase().includes(search.toLowerCase()));
  const categories = ['전체', ...Array.from(new Set(allPlaces.map((place) => place.category)))];
  const scheduledPlaceIds = [...new Set(trip.itinerary?.flatMap((day) => day.items.flatMap((item) => item.kind === 'place' && item.placeId ? [item.placeId] : [])) ?? [])];
  const scheduledPlaces = scheduledPlaceIds.map((id) => getTripPlace(trip, id)).filter((place): place is TripPlace => Boolean(place));

  const openPlaceDetail = (place: TripPlace) => {
    setActiveId(place.id);
    setDetailPlace({
      name: place.name,
      address: place.area,
      description: place.summary ?? place.description ?? '사용자가 가져온 장소입니다.',
      image: place.image,
      category: place.category,
      area: place.area,
      rating: place.rating,
      reviewCount: place.reviews,
      duration: trip.placeDurations?.[place.id] ?? place.duration,
      price: place.price,
      badge: place.reservation ? '예약 권장' : place.closed,
      googleMapsQuery: place.sourceUrl ?? `${place.name} ${place.area}`,
    });
  };
  const addPlace = (place: TripPlace) => {
    const added = addPlaceToItinerary(trip.id, place.id);
    setItineraryNotice(added ? `${place.name}을(를) 일정에 추가했어요.` : '이미 일정에 추가된 장소예요.');
  };
  const removePlace = (place: TripPlace) => {
    const removed = removePlaceFromItinerary(trip.id, place.id);
    setItineraryNotice(removed ? `${place.name}을(를) 일정에서 제거했어요.` : '일정에서 제거할 장소를 찾지 못했어요.');
  };

  useEffect(() => {
    if (!itineraryNotice) return;
    const timer = window.setTimeout(() => setItineraryNotice(null), 2600);
    return () => window.clearTimeout(timer);
  }, [itineraryNotice]);

  const preparePreview = (places: TripPlace[], source: string) => {
    setPreviewPlaces(places);
    setPreviewSource(source);
    setImportedIds(places.map((place) => place.id));
    setImportDurations(Object.fromEntries(places.map((place) => [place.id, trip.placeDurations?.[place.id] ?? place.duration])));
  };

  const loadDemoImport = () => preparePreview(PLACES.slice(0, 4), '목 데이터');

  const openImportDialog = () => {
    setImportMode('links');
    setImportError('');
    setPreviewPlaces([]);
    setPreviewSource('');
    setImportedIds([]);
    setLinkRows([{ id: 'link-1', url: '', name: '', area: '', latitude: '', longitude: '' }]);
    setImportOpen(true);
  };

  const changeImportMode = (mode: 'links' | 'file' | 'demo') => {
    setImportMode(mode);
    setImportError('');
    if (mode === 'demo') loadDemoImport();
    else {
      setPreviewPlaces([]);
      setPreviewSource('');
      setImportedIds([]);
    }
  };

  const updateLinkRow = (id: string, patch: Partial<MapLinkRow>) => setLinkRows((rows) => rows.map((row) => row.id === id ? { ...row, ...patch } : row));
  const addLinkRow = () => setLinkRows((rows) => [...rows, { id: `link-${Date.now()}-${rows.length}`, url: '', name: '', area: '', latitude: '', longitude: '' }]);
  const removeLinkRow = (id: string) => setLinkRows((rows) => rows.length === 1 ? rows.map((row) => ({ ...row, url: '', name: '', area: '', latitude: '', longitude: '', error: undefined })) : rows.filter((row) => row.id !== id));

  const analyzeLinks = () => {
    const parsed: ImportedPlace[] = [];
    const nextRows = linkRows.map((row) => {
      if (!row.url.trim()) return { ...row, error: 'Google Maps 링크를 입력해 주세요.' };
      try {
        parsed.push(...parseGoogleMapsUrl(row.url));
        return { ...row, error: undefined };
      } catch (error) {
        if (row.name.trim()) {
          const latitude = row.latitude.trim() ? Number(row.latitude) : undefined;
          const longitude = row.longitude.trim() ? Number(row.longitude) : undefined;
          if ((latitude === undefined) !== (longitude === undefined) || (latitude !== undefined && (!Number.isFinite(latitude) || !Number.isFinite(longitude)))) {
            return { ...row, error: '위도와 경도는 둘 다 올바른 숫자로 입력해 주세요.' };
          }
          parsed.push(createManualUrlPlace({ url: row.url, name: row.name.trim(), area: row.area.trim(), latitude, longitude }));
          return { ...row, error: undefined };
        }
        return { ...row, error: error instanceof Error ? error.message : '링크를 분석하지 못했어요.' };
      }
    });
    setLinkRows(nextRows);
    if (parsed.length > 0) {
      preparePreview(Array.from(new Map(parsed.map((place) => [place.id, place])).values()), 'Google Maps 링크');
      setImportError('');
    } else {
      setPreviewPlaces([]);
      setImportedIds([]);
      setImportError('분석된 장소가 없어요. 단축 링크는 장소명을 직접 입력해 보완할 수 있습니다.');
    }
  };

  const importFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setImportLoading(true);
    setImportError('');
    try {
      const places = await parsePlaceFile(file);
      preparePreview(places, file.name);
    } catch (error) {
      setPreviewPlaces([]);
      setImportedIds([]);
      setImportError(error instanceof Error ? error.message : '파일을 가져오지 못했어요.');
    } finally {
      setImportLoading(false);
    }
  };

  const confirmImport = () => {
    const selectedDurations = Object.fromEntries(importedIds.map((id) => [id, importDurations[id] ?? 60]));
    const customPlaces = previewPlaces.filter(isImportedPlace);
    importPlaces(trip.id, customPlaces, importedIds, selectedDurations);
    setImportOpen(false);
  };

  return <>
    <div className="split-page places-page"><section className="split-list"><div className="agent-summary"><Sparkles size={15} /><strong>{allPlaces.length}곳을 확인할 수 있어요.</strong><span>{Object.keys(trip.importedPlaces ?? {}).length > 0 ? `가져온 장소 ${Object.keys(trip.importedPlaces ?? {}).length}곳을 포함합니다.` : '관심사에 맞는 곳을 위로 올려뒀습니다.'}</span></div><div className="place-controls"><div className="input-with-icon"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="장소 검색" /></div><div className="category-tabs">{categories.map((item) => <button className={category === item ? 'is-active' : ''} key={item} onClick={() => setCategory(item)}>{item} <span>{item === '전체' ? allPlaces.length : allPlaces.filter((place) => place.category === item).length}</span></button>)}</div><div className="import-plan-trigger"><button className="button button--secondary button--small" aria-describedby="import-plan-tooltip" onClick={openImportDialog}><Link2 size={14} /> 내 계획 가져오기</button><span role="tooltip" id="import-plan-tooltip">여러 Google Maps 링크 또는 My Maps 파일에서 장소와 예상 소요시간을 가져옵니다.</span></div></div><div className="place-list">{filtered.map((place) => { const selected = trip.selectedPlaceIds.includes(place.id); const duration = trip.placeDurations?.[place.id] ?? place.duration; return <article className={`place-card ${selected ? 'is-selected' : ''} ${activeId === place.id ? 'is-active' : ''}`} key={place.id} onMouseEnter={() => setActiveId(place.id)} onMouseLeave={() => setActiveId(null)}><button className="place-card__select" onClick={() => togglePlace(trip.id, place.id)} aria-label={`${place.name} 선택`}>{selected && <Check size={13} />}</button><button type="button" className={`place-card__add ${scheduledPlaceIds.includes(place.id) ? 'is-added' : ''}`} disabled={scheduledPlaceIds.includes(place.id)} onClick={() => addPlace(place)} aria-label={`${place.name} 일정에 추가`}>{scheduledPlaceIds.includes(place.id) ? <Check size={14} /> : <Plus size={14} />}</button><button className="place-card__detail" onClick={() => openPlaceDetail(place)}><div className={`place-image ${place.image ? '' : 'is-placeholder'}`} style={place.image ? { backgroundImage: `url(${place.image})` } : undefined}>{!place.image && <MapPin size={22} />}</div><div><div className="place-card__title"><h3>{place.name}</h3>{place.sourceType && <span className="status-badge">가져옴</span>}{place.closed && <span className="danger-badge">{place.closed}</span>}</div><p>{place.category} · {place.area}</p><div className="place-rating">{place.rating !== undefined ? <><Star size={13} />{place.rating} <span>({place.reviews?.toLocaleString() ?? 0})</span> · </> : place.latitude !== undefined ? <><MapPin size={13} /> {place.latitude.toFixed(4)}, {place.longitude?.toFixed(4)} · </> : null}<Clock3 size={13} /> {Math.floor(duration / 60) ? `${Math.floor(duration / 60)}시간 ` : ''}{duration % 60 || ''}{duration % 60 ? '분' : ''}</div><small>{place.summary ?? place.description ?? '사용자가 가져온 장소입니다.'}</small><div className="place-tags">{place.price && <span>{place.price}</span>}{place.reservation && <span className="warning-badge">예약 권장</span>}<em><Sparkles size={12} />{place.note ?? place.sourceLabel ?? '사용자 장소'}</em></div></div></button></article>; })}</div><div className="selection-summary"><strong><Check size={15} /> {trip.selectedPlaceIds.length}곳 선택</strong><span>예상 소요 {Math.round(trip.selectedPlaceIds.reduce((sum, id) => sum + (trip.placeDurations?.[id] ?? getTripPlace(trip, id)?.duration ?? 0), 0) / 60)}시간</span><span>하루 평균 {(trip.selectedPlaceIds.length / Math.max(1, getNights(trip.startDate, trip.endDate) + 1)).toFixed(1)}곳</span></div></section><aside className="split-map"><MapPanel places={allPlaces} selectedIds={trip.selectedPlaceIds} activeId={activeId} onMarkerClick={setActiveId} focusActive stay={STAYS.find((stay) => stay.id === trip.selectedStayId) ?? null} /></aside></div>
    <button type="button" className="place-itinerary-fab" onClick={() => setAddedPlacesOpen(true)}><ListChecks size={16} /> 일정에 추가한 장소 <strong>{scheduledPlaces.length}</strong></button>
    {itineraryNotice && <div className="place-itinerary-cta__notice" role="status">{itineraryNotice}</div>}
    {addedPlacesOpen && <div className="place-itinerary-manager__backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setAddedPlacesOpen(false); }}><section className="place-itinerary-manager" role="dialog" aria-modal="true" aria-labelledby="place-itinerary-manager-title"><header><div><span className="eyebrow">SCHEDULED PLACES</span><h2 id="place-itinerary-manager-title">일정에 추가한 장소 <em>{scheduledPlaces.length}</em></h2><p>가져온 장소를 포함해 일정에 바로 배치된 장소예요.</p></div><button type="button" className="place-itinerary-manager__close" aria-label="닫기" onClick={() => setAddedPlacesOpen(false)}><CircleX size={18} /></button></header>{scheduledPlaces.length === 0 ? <div className="place-itinerary-manager__empty"><MapPin size={28} /><strong>아직 추가한 장소가 없어요</strong><span>장소 카드의 + 버튼으로 일정에 바로 추가할 수 있어요.</span></div> : <div className="place-itinerary-manager__list">{scheduledPlaces.map((place) => <article key={place.id}><div className={`place-itinerary-manager__image ${place.image ? '' : 'is-placeholder'}`} style={place.image ? { backgroundImage: `url(${place.image})` } : undefined}>{!place.image && <MapPin size={18} />}</div><div><strong>{place.name}</strong><span>{place.category} · {place.area}</span><small><Clock3 size={12} /> {formatDurationLabel(trip.placeDurations?.[place.id] ?? place.duration)}</small></div><button type="button" onClick={() => removePlace(place)}><Trash2 size={13} /> 제거</button></article>)}</div>}</section></div>}
    <PlaceDetailModal place={detailPlace} onClose={() => setDetailPlace(null)} />
    {importOpen && (
      <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setImportOpen(false); }}>
        <section className="modal-card import-plan-dialog" role="dialog" aria-modal="true" aria-labelledby="import-plan-title">
          <header><div><span className="eyebrow">IMPORT PLAN</span><h2 id="import-plan-title">내 계획 가져오기</h2><p>여러 장소 링크를 분석하거나 My Maps에서 내보낸 파일을 브라우저에서 바로 가져오세요.</p></div><button className="icon-button" aria-label="닫기" onClick={() => setImportOpen(false)}><CircleX size={19} /></button></header>
          <section className="import-dialog-section" aria-labelledby="import-source-title">
            <div className="import-section-heading"><div><span>1</span><div><strong id="import-source-title">장소 가져오기 방식</strong><small>링크·파일·데모 중 하나를 선택하세요.</small></div></div><a className="button button--secondary button--small" href="https://www.google.com/maps" target="_blank" rel="noreferrer"><Link2 size={14} /> Google 지도 열기</a></div>
            <div className="import-source-tabs" role="tablist" aria-label="가져오기 방식"><button type="button" role="tab" aria-selected={importMode === 'links'} className={importMode === 'links' ? 'is-active' : ''} onClick={() => changeImportMode('links')}>여러 장소 링크</button><button type="button" role="tab" aria-selected={importMode === 'file'} className={importMode === 'file' ? 'is-active' : ''} onClick={() => changeImportMode('file')}>My Maps 파일</button><button type="button" role="tab" aria-selected={importMode === 'demo'} className={importMode === 'demo' ? 'is-active' : ''} onClick={() => changeImportMode('demo')}>데모 보기</button></div>
            {importMode === 'links' && <div className="multi-link-import"><div className="map-link-list">{linkRows.map((row, index) => <div className={`map-link-row ${row.error ? 'has-error' : ''}`} key={row.id}><div className="map-link-row__main"><span>{index + 1}</span><input type="url" value={row.url} onChange={(event) => updateLinkRow(row.id, { url: event.target.value })} placeholder="https://maps.app.goo.gl/... 또는 전체 Google Maps URL" aria-label={`장소 링크 ${index + 1}`} /><button type="button" className="icon-button" aria-label={`링크 ${index + 1} 삭제`} onClick={() => removeLinkRow(row.id)}><Trash2 size={15} /></button></div>{row.error && <div className="manual-link-place"><p role="alert">{row.error}</p><div><label>장소명<input value={row.name} onChange={(event) => updateLinkRow(row.id, { name: event.target.value })} placeholder="예: 센소지" /></label><label>지역·주소<input value={row.area} onChange={(event) => updateLinkRow(row.id, { area: event.target.value })} placeholder="예: 도쿄 아사쿠사" /></label><label>위도 (선택)<input inputMode="decimal" value={row.latitude} onChange={(event) => updateLinkRow(row.id, { latitude: event.target.value })} placeholder="35.7148" /></label><label>경도 (선택)<input inputMode="decimal" value={row.longitude} onChange={(event) => updateLinkRow(row.id, { longitude: event.target.value })} placeholder="139.7967" /></label></div><small>단축 링크는 장소명을 입력하면 링크 원본과 함께 사용자 장소로 저장할 수 있어요.</small></div>}</div>)}</div><div className="multi-link-actions"><button type="button" className="button button--secondary button--small" onClick={addLinkRow}><Plus size={14} /> 링크 추가</button><button type="button" className="button button--primary" onClick={analyzeLinks}>입력한 링크 분석</button></div></div>}
            {importMode === 'file' && <div className="file-import-panel"><label className="file-drop-button"><Link2 size={20} /><strong>{importLoading ? '파일을 읽고 있어요…' : 'KML · KMZ · CSV · GeoJSON 파일 선택'}</strong><span>My Maps에서 내보낸 파일을 서버 전송 없이 브라우저에서 분석합니다. 최대 10MB·200곳</span><input type="file" accept=".kml,.kmz,.csv,.json,.geojson,application/vnd.google-earth.kml+xml,application/vnd.google-earth.kmz" disabled={importLoading} onChange={importFile} /></label><small>공개·비공개 My Maps 공유 링크 대신 지도 메뉴에서 KML/KMZ로 내보내 주세요.</small></div>}
            {importMode === 'demo' && <div className="demo-import-panel"><Sparkles size={18} /><div><strong>실제 파일 없이 흐름 확인</strong><span>도쿄 목 장소 4곳으로 선택과 예상 소요시간 입력을 체험합니다.</span></div><button type="button" className="button button--secondary button--small" onClick={loadDemoImport}>데모 다시 불러오기</button></div>}
            {importError && <p className="form-error" role="alert">{importError}</p>}
          </section>
          <div className="import-preview" aria-labelledby="place-duration-title"><div className="import-preview__heading"><div><span>2</span><div><strong id="place-duration-title">각 장소에서 예상 소요 시간</strong><small>{previewPlaces.length ? '가져올 장소를 고르고 머무를 시간을 설정하세요.' : '링크를 분석하거나 파일·데모 데이터를 불러오면 여기에 표시됩니다.'}</small></div></div><em>{importedIds.length}곳 선택{previewSource ? ` · ${previewSource}` : ''}</em></div>{previewPlaces.length === 0 ? <div className="import-preview-empty"><MapPin size={24} /><strong>아직 분석된 장소가 없어요</strong><span>위에서 가져오기 방식을 선택해 주세요.</span></div> : previewPlaces.map((place) => { const selected = importedIds.includes(place.id); return <article className={selected ? 'is-selected' : ''} key={place.id}><button type="button" className="import-place-toggle" aria-pressed={selected} onClick={() => setImportedIds(selected ? importedIds.filter((id) => id !== place.id) : [...importedIds, place.id])}><span>{selected && <Check size={13} />}</span><div><strong>{place.name}</strong><small>{place.category} · {place.area}{place.latitude !== undefined ? ` · ${place.latitude.toFixed(4)}, ${place.longitude?.toFixed(4)}` : ''}</small></div></button><label><Clock3 size={14} /> 예상 소요 시간<select value={importDurations[place.id] ?? place.duration} disabled={!selected} onChange={(event) => setImportDurations({ ...importDurations, [place.id]: Number(event.target.value) })}>{[30, 60, 90, 120, 150, 180, 240].map((minutes) => <option value={minutes} key={minutes}>{minutes < 60 ? `${minutes}분` : `${Math.floor(minutes / 60)}시간${minutes % 60 ? ` ${minutes % 60}분` : ''}`}</option>)}</select></label></article>; })}</div>
          <footer><button className="button button--secondary" type="button" onClick={() => setImportOpen(false)}>취소</button><button className="button button--primary" type="button" disabled={importedIds.length === 0} onClick={confirmImport}>선택한 장소 가져오기</button></footer>
        </section>
      </div>
    )}
  </>;
}

function ItineraryStep({ trip }: { trip: Trip }) {
  const applyAgentPlan = useTripStore((state) => state.applyAgentPlan);
  const moveItem = useTripStore((state) => state.moveItineraryItem);
  const addPlaces = useTripStore((state) => state.addPlacesToItinerary);
  const removeItem = useTripStore((state) => state.removeItineraryItem);
  const updateItemDuration = useTripStore((state) => state.updateItineraryItemDuration);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [tab, setTab] = useState<'schedule' | 'expense' | 'checklist'>('schedule');
  const [dragged, setDragged] = useState<{ dayId: string; itemId: string } | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [addDayId, setAddDayId] = useState<string | null>(null);
  const [modalSelectedIds, setModalSelectedIds] = useState<string[]>([]);
  const [modalActiveId, setModalActiveId] = useState<string | null>(null);
  const [durationEditorId, setDurationEditorId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const generate = (id: string) => { if (id === trip.id) setGenerating(true); };
  const durationEditorRef = useRef<HTMLDivElement>(null);
  const allPlaces = getTripPlaces(trip);

  useEffect(() => {
    if (!durationEditorId) return;
    const closeEditor = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent && event.key !== 'Escape') return;
      if (event instanceof MouseEvent && durationEditorRef.current?.contains(event.target as Node)) return;
      setDurationEditorId(null);
    };
    document.addEventListener('mousedown', closeEditor);
    document.addEventListener('keydown', closeEditor);
    return () => {
      document.removeEventListener('mousedown', closeEditor);
      document.removeEventListener('keydown', closeEditor);
    };
  }, [durationEditorId]);

  if (generating) return <div className="stream-page"><PageHeading eyebrow="AGENT · SUPERVISOR" title="선택한 장소로 일정을 만들고 있어요" description="Supervisor가 일정 생성과 검증, 필요한 재계획까지 진행합니다." /><AgentPanel type="일정" task="itineraryGenerate" input={{ trip }} onDone={(payload) => { const result = readAgentPlan(payload); if (result) applyAgentPlan(trip.id, result.itinerary, result.verification); setGenerating(false); }} onAbort={() => setGenerating(false)} /><SkeletonCards count={3} /></div>;

  if (!trip.itinerary) return <div className="generation-page"><PageHeading eyebrow="STEP 6 · 일정 생성" title="선택한 장소로 일정을 설계할게요" description={`${trip.selectedPlaceIds.length}곳의 위치와 영업시간, 이동 동선을 함께 고려합니다.${trip.persona.companionDescription?.trim() ? ' 저장한 동행 메모는 AI 연결 시 생성 조건에 함께 전달됩니다.' : ''}`} /><div className="generation-visual"><div className="generation-orbit"><WandSparkles size={28} /></div><div><span><CheckCircle2 size={15} /> 장소를 지역별로 묶기</span><span><CheckCircle2 size={15} /> 영업시간과 휴관일 확인</span><span><Circle size={15} /> 이동 시간 계산</span><span><Circle size={15} /> 일자별 일정 배치</span></div></div><button className="button button--primary button--large" onClick={() => generate(trip.id)}><Sparkles size={17} /> AI로 일정 만들기</button></div>;

  const allPlaceIds = trip.itinerary.flatMap((day) => day.items.map((item) => item.placeId).filter((id): id is string => Boolean(id)));
  const scheduledPlaceIds = new Set(allPlaceIds);
  const modalPlaces = allPlaces.filter((place) => trip.selectedPlaceIds.includes(place.id));
  const targetDay = trip.itinerary.find((day) => day.id === addDayId);

  const handleDrop = (event: React.DragEvent, targetDayId: string, targetIndex: number) => {
    event.preventDefault();
    event.stopPropagation();
    if (dragged) moveItem(trip.id, dragged.dayId, dragged.itemId, targetDayId, targetIndex);
    setDragged(null);
    setDropTarget(null);
  };

  const openAddPlaces = (dayId: string) => {
    setAddDayId(dayId);
    setModalSelectedIds([]);
    setModalActiveId(null);
  };

  const confirmAddPlaces = () => {
    if (!addDayId || modalSelectedIds.length === 0) return;
    addPlaces(trip.id, addDayId, modalSelectedIds);
    setAddDayId(null);
    setModalSelectedIds([]);
  };

  return <>
    <div className="split-page itinerary-page"><section className="split-list"><div className="agent-summary"><Sparkles size={15} /><strong>{trip.itinerary.length}일 일정을 완성했어요.</strong><span>{trip.persona.companionDescription?.trim() ? `저장된 동행 메모: ${trip.persona.companionDescription}` : '장소 카드를 드래그해 원하는 날짜와 순서로 직접 수정할 수 있어요. 항공·체크인 시간은 고정됩니다.'}</span></div><div className="itinerary-toolbar"><div className="tabs"><button className={tab === 'schedule' ? 'is-active' : ''} onClick={() => setTab('schedule')}>일정</button><button className={tab === 'expense' ? 'is-active' : ''} onClick={() => setTab('expense')}>지출</button><button className={tab === 'checklist' ? 'is-active' : ''} onClick={() => setTab('checklist')}>준비물</button></div></div>{tab === 'schedule' && <div className="day-list">{trip.itinerary.map((day, dayIndex) => <section className="day-section" key={day.id}><header><ChevronDown size={16} /><i style={{ background: `var(--day-${(dayIndex % 6) + 1})` }} /><div><div><strong>Day {dayIndex + 1}</strong><span>{day.date.slice(5)} · {day.title}</span></div><small>{day.items.filter((item) => item.kind === 'place').length}곳 · 활동 {Math.round(day.items.reduce((sum, item) => sum + item.duration, 0) / 60)}시간 · 이동 {day.items.reduce((sum, item) => sum + (item.travelMinutes ?? 0), 0)}분</small></div></header><div className="day-items">{day.items.map((item, itemIndex) => { const place = getTripPlace(trip, item.placeId ?? ''); const placeNumber = day.items.slice(0, itemIndex + 1).filter((value) => value.kind === 'place').length; const targetKey = `${day.id}:${itemIndex}`; return <div className={`itinerary-drop-wrap ${dropTarget === targetKey ? 'is-drop-target' : ''}`} key={item.id} onDragOver={(event) => { event.preventDefault(); setDropTarget(targetKey); }} onDragLeave={() => setDropTarget((current) => current === targetKey ? null : current)} onDrop={(event) => handleDrop(event, day.id, itemIndex)}><article draggable={item.kind === 'place'} className={`itinerary-card ${activeId === item.placeId ? 'is-active' : ''} ${dragged?.itemId === item.id ? 'is-dragging' : ''}`} onDragStart={(event) => { if (item.kind !== 'place' || (event.target as HTMLElement).closest('button, input')) { event.preventDefault(); return; } event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', item.id); setDragged({ dayId: day.id, itemId: item.id }); }} onDragEnd={() => { setDragged(null); setDropTarget(null); }} onMouseEnter={() => setActiveId(item.placeId ?? null)} onMouseLeave={() => setActiveId(null)}><div className="itinerary-card__identity">{item.kind === 'place' && <GripVertical className="drag-handle" size={15} />}<span className={`item-number ${item.kind !== 'place' ? 'is-icon' : ''}`} style={{ background: item.kind === 'place' ? `var(--day-${(dayIndex % 6) + 1})` : undefined }}>{item.kind === 'place' ? placeNumber : item.kind === 'flight' ? <Plane size={12} /> : item.kind === 'stay' ? <BedDouble size={12} /> : <UtensilsCrossed size={12} />}</span><time>{item.time}</time></div><div className="itinerary-card__body"><strong>{item.title}</strong><span>{place ? `${place.category} · ${formatDurationLabel(item.duration)}` : item.kind === 'flight' ? '항공 이동' : '여행 일정'}</span>{place && (place.rating !== undefined || place.price) && <small>{place.rating !== undefined && <><Star size={12} /> {place.rating}</>}{place.rating !== undefined && place.price ? ' · ' : ''}{place.price}</small>}{item.kind === 'place' && <div ref={durationEditorId === item.id ? durationEditorRef : undefined} className={`duration-control ${durationEditorId === item.id ? 'is-open' : ''}`}><button type="button" className="duration-trigger" aria-expanded={durationEditorId === item.id} onClick={() => setDurationEditorId((current) => current === item.id ? null : item.id)}><Clock3 size={13} /><span>체류 시간</span><strong>{formatDurationLabel(item.duration)}</strong><ChevronDown size={13} /></button>{durationEditorId === item.id && <div className="duration-popover"><div className="duration-popover__value"><span>예상 소요 시간</span><strong>{formatDurationLabel(item.duration)}</strong></div><div className="duration-range"><input type="range" min="30" max="480" step="15" value={item.duration} aria-label={`${item.title} 체류 시간`} onChange={(event) => updateItemDuration(trip.id, day.id, item.id, Number(event.target.value))} /><div className="duration-range__bars" aria-hidden>{Array.from({ length: 16 }, (_, index) => <i className={index < Math.ceil(item.duration / 30) ? 'is-filled' : ''} key={index} />)}</div><div className="duration-range__labels"><span>30분</span><span>8시간</span></div></div></div>}</div>}</div><div className="itinerary-item-actions">{place?.closed ? <TriangleAlert className="warning-icon" size={15} /> : <CheckCircle2 className="success-icon" size={15} />}{item.kind === 'place' && <button type="button" className="button button--ghost" aria-label={`${item.title} 일정에서 삭제`} onClick={() => { if (window.confirm(`${item.title}을(를) 일정에서 삭제할까요?`)) removeItem(trip.id, day.id, item.id); }}><Trash2 size={14} /></button>}</div></article>{itemIndex < day.items.length - 1 && <div className="travel-connector"><span /><Footprints size={13} /><strong>{item.travelMinutes ?? 12}분</strong><em>{item.travelMode}</em></div>}</div>; })}<div className={`day-drop-zone ${dropTarget === `${day.id}:end` ? 'is-active' : ''}`} onDragOver={(event) => { event.preventDefault(); setDropTarget(`${day.id}:end`); }} onDragLeave={() => setDropTarget(null)} onDrop={(event) => handleDrop(event, day.id, day.items.length)}>여기에 놓아 마지막으로 이동</div></div><button className="add-place-button" onClick={() => openAddPlaces(day.id)}><Plus size={14} /> 장소 추가</button></section>)}</div>}{tab === 'expense' && <ExpensePanel trip={trip} />}{tab === 'checklist' && <ChecklistPanel />}</section><aside className="split-map"><MapPanel places={allPlaces} selectedIds={allPlaceIds} activeId={activeId} onMarkerClick={setActiveId} showRoute stay={STAYS.find((stay) => stay.id === trip.selectedStayId) ?? null} /></aside></div>
    {addDayId && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setAddDayId(null); }}><section className="modal-card itinerary-add-dialog" role="dialog" aria-modal="true" aria-labelledby="add-place-title"><header><div><span className="eyebrow">ADD TO ITINERARY</span><h2 id="add-place-title">{targetDay?.title ?? '일정'}에 장소 추가</h2><p>가고 싶은 곳에서 선택한 장소를 지도와 함께 확인하세요.</p></div><button className="icon-button" aria-label="닫기" onClick={() => setAddDayId(null)}><CircleX size={19} /></button></header><div className="itinerary-add-layout"><div className="itinerary-add-map"><MapPanel places={allPlaces} selectedIds={modalPlaces.map((place) => place.id)} activeId={modalActiveId} onMarkerClick={setModalActiveId} /></div><div className="itinerary-add-list">{modalPlaces.length === 0 ? <div className="empty-state"><MapPin size={30} /><h3>선택한 장소가 없어요</h3><p>가고 싶은 곳 단계에서 장소를 먼저 선택해 주세요.</p></div> : modalPlaces.map((place) => { const scheduled = scheduledPlaceIds.has(place.id); const selected = modalSelectedIds.includes(place.id); return <button type="button" disabled={scheduled} aria-pressed={selected} className={selected ? 'is-selected' : ''} key={place.id} onMouseEnter={() => setModalActiveId(place.id)} onMouseLeave={() => setModalActiveId(null)} onClick={() => setModalSelectedIds(selected ? modalSelectedIds.filter((id) => id !== place.id) : [...modalSelectedIds, place.id])}><div className={`place-image ${place.image ? '' : 'is-placeholder'}`} style={place.image ? { backgroundImage: `url(${place.image})` } : undefined}>{!place.image && <MapPin size={18} />}</div><div><strong>{place.name}</strong><span>{place.category} · {place.area}</span><small><Clock3 size={12} /> {trip.placeDurations?.[place.id] ?? place.duration}분{place.price ? ` · ${place.price}` : ' · 사용자 장소'}</small></div><em>{scheduled ? '일정에 있음' : selected ? '추가 예정' : '선택'}</em></button>; })}</div></div><footer><span>{modalSelectedIds.length}곳 선택</span><button className="button button--secondary" onClick={() => setAddDayId(null)}>취소</button><button className="button button--primary" disabled={modalSelectedIds.length === 0} onClick={confirmAddPlaces}>선택한 장소 추가</button></footer></section></div>}
  </>;
}

function ExpensePanel({ trip }: { trip: Trip }) {
  const flight = FLIGHTS.find((item) => item.id === trip.selectedFlightId)?.price ?? 0;
  const stay = STAYS.find((item) => item.id === trip.selectedStayId)?.total ?? 0;
  const scheduledPlaceIds = new Set(trip.itinerary?.flatMap((day) => day.items.map((item) => item.placeId).filter((placeId): placeId is string => Boolean(placeId))) ?? []);
  const activities = scheduledPlaceIds.size * 22000;
  const total = flight + stay + activities + 152000;
  return <div className="expense-panel"><header><div><span>예상 지출</span><strong>{total.toLocaleString()}원</strong></div><div className="budget-bar"><span style={{ width: `${Math.min(100, (total / 1600000) * 100)}%` }} /></div><small>예산 1,600,000원 중 {Math.round((total / 1600000) * 100)}% 사용</small></header>{[['항공권', flight], ['숙소', stay], ['입장료 · 활동', activities], ['식사 (추정)', 120000], ['교통 (추정)', 32000]].map(([label, amount]) => <div key={String(label)}><span>{label}</span><strong>{Number(amount).toLocaleString()}원</strong></div>)}</div>;
}

function ChecklistPanel() {
  return <div className="checklist-panel"><h3>예약 필요</h3>{['팀랩 플래닛 사전 예약', '시부야 스카이 입장 시간 예약'].map((item, index) => <label key={item}><input type="checkbox" defaultChecked={index === 0} /><span>{item}</span><small>Day {index + 2}</small></label>)}<h3>날씨 대비</h3><label><input type="checkbox" /><span>접이식 우산 준비</span><small>여행 기간 중 비 예보 가능</small></label><button><Plus size={14} /> 항목 추가</button></div>;
}

function VerifyStep({ trip }: { trip: Trip }) {
  const router = useRouter();
  const applyAgentVerification = useTripStore((state) => state.applyAgentVerification);
  const verificationIsCurrent = isVerificationCurrent(trip);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  if (running) return <div className="stream-page"><PageHeading eyebrow="AGENT · VERIFICATION" title="일정을 검증하고 있어요" description="운영시간, 이동 가능성, 예산과 여행 페이스를 실제 검증 에이전트가 확인합니다." /><AgentPanel type="일정" task="itineraryVerify" input={{ trip }} onDone={(payload) => { const checks = readAgentVerification(payload); if (checks) applyAgentVerification(trip.id, checks); setRunning(false); }} onAbort={() => setRunning(false)} /><SkeletonCards count={3} /></div>;
  if ((!trip.verification || !verificationIsCurrent) && !running) return <div className="verify-intro"><div className="verify-shield"><ShieldCheck size={36} /></div><PageHeading eyebrow="STEP 7 · 최종 점검" title={trip.verification ? '수정한 일정을 다시 검증할게요' : '일정을 검증할게요'} description={trip.verification ? '직접 수정한 일정과 기존 검증 결과를 구분해 변경된 시간표를 다시 확인합니다.' : '휴관일, 이동 시간, 예산, 접근성 등 10가지를 확인합니다.'} /><div className="verify-intro__summary"><span><CalendarDays size={16} />{trip.itinerary?.length ?? 0}일 일정</span><span><MapPin size={16} />방문지 {trip.selectedPlaceIds.length}곳</span><span><ListChecks size={16} />검사 항목 10개</span></div><button className="button button--primary button--large" onClick={() => { setProgress(0); setRunning(true); }}><ShieldCheck size={17} /> {trip.verification ? '수정 일정 다시 검증' : '검증 시작'}</button></div>;
  if (running) return <div className="verify-running"><section><div className="verify-running__header"><div><h1>일정을 검증하고 있어요</h1><span>{progress}/10</span></div><div className="verification-progress"><span style={{ width: `${progress * 10}%` }} /></div></div><div className="verify-checklist">{['영업시간 · 휴관일', '이동 시간 실현성', '항공 도착 · 출발 여유', '숙소 체크인 · 체크아웃', '하루 일정량', '예산', '접근성', '관심사 반영', '사전 예약 필요', '시즌 · 날씨'].map((label, index) => <div className={index === progress ? 'is-running' : ''} key={label}>{index < progress ? <CheckCircle2 size={16} /> : index === progress ? <Loader2 className="spin" size={16} /> : <Circle size={16} />}<strong>{label}</strong><span>{index < progress ? (index === 0 ? '충돌 1' : index === 1 || index === 4 ? '주의 1' : '정상') : index === progress ? '검사 중…' : '대기'}</span></div>)}</div></section><ReasoningConsole progress={progress} /></div>;
  const checks = trip.verification ?? [];
  const pass = checks.filter((check) => check.status === 'pass').length;
  const warnings = checks.filter((check) => check.status === 'warning').length;
  const conflicts = checks.filter((check) => check.status === 'conflict').length;
  return <div className="verify-report"><section className="score-card"><div><span className="eyebrow">VERIFICATION COMPLETE</span><h1>검증을 마쳤어요</h1><p>충돌 {conflicts}건을 해결하면 일정이 완성돼요.</p></div><div className="score-counts"><span className="pass"><strong>{pass}</strong>정상</span><span className="warning"><strong>{warnings}</strong>주의</span><span className="conflict"><strong>{conflicts}</strong>충돌</span></div></section><div className="report-heading"><h2>해결해야 할 것</h2><div><button className="button button--secondary button--small" type="button" onClick={() => router.push(`/plan/${trip.id}/itinerary`)}><GripVertical size={14} /> 일정 직접 수정</button><button className="button button--primary button--small"><WandSparkles size={14} /> 자동 수정 모두 적용</button></div></div><div className="issue-list">{checks.filter((check) => check.status === 'warning' || check.status === 'conflict').map((check, index) => <article className={`issue-card is-${check.status}`} key={check.id}><header><span>{check.status === 'conflict' ? <CircleX size={14} /> : <TriangleAlert size={14} />}{check.status === 'conflict' ? '충돌' : '주의'}</span><code>[{check.id}]</code></header><h3>{check.message}</h3><p>{index === 0 ? '도쿄 국립박물관은 매주 월요일 휴관입니다. 같은 지역을 방문하는 다른 날로 옮기는 것이 좋아요.' : '현재 일정과 여행 페이스를 비교해 조정이 필요한 항목입니다.'}</p><div className="evidence"><strong>근거</strong><span>· 장소 운영 정보와 방문 예정 시간을 대조했습니다.</span><span>· 현재 이동 경로와 체류 시간을 함께 계산했습니다.</span></div><div className="fix-suggestion"><Sparkles size={14} /><div><strong>제안</strong><span>{index === 0 ? 'Day 3 오전으로 옮기면 같은 우에노 권역에서 이동할 수 있어요.' : '마지막 방문지를 다음 날로 옮겨 여유를 확보해요.'}</span><small>예상 이동 시간 +4분</small></div></div><footer><button className="button button--secondary button--small" type="button" onClick={() => router.push(`/plan/${trip.id}/itinerary`)}>일정에서 보기</button><button className="button button--ghost button--small">무시하기</button><button className="button button--primary button--small">이 수정 적용</button></footer></article>)}</div><details className="passed-checks"><summary><CheckCircle2 size={16} /> 통과한 항목 {pass}개 <ChevronDown size={15} /></summary>{checks.filter((check) => check.status === 'pass').map((check) => <div key={check.id}><Check size={14} /><strong>{check.label}</strong><span>{check.message}</span></div>)}</details></div>;
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
