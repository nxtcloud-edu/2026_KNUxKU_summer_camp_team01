export type StepId =
  | 'city'
  | 'persona'
  | 'flights'
  | 'stays'
  | 'places'
  | 'itinerary'
  | 'verify';

export type City = {
  id: string;
  name: string;
  nameEn: string;
  country: string;
  flag: string;
  currency: string;
  timezone: string;
  image: string;
  color: string;
};

export type PlaceCategory = '명소' | '역사' | '자연' | '미술관' | '맛집' | '쇼핑';

export type Place = {
  id: string;
  name: string;
  localName?: string;
  category: PlaceCategory;
  area: string;
  rating: number;
  reviews: number;
  duration: number;
  price: string;
  summary: string;
  note: string;
  image: string;
  x: number;
  y: number;
  closed?: string;
  reservation?: boolean;
};

export type FlightOffer = {
  id: string;
  airline: string;
  code: string;
  price: number;
  outbound: string;
  inbound: string;
  duration: string;
  tag: string;
  note: string;
};

export type StayOffer = {
  id: string;
  name: string;
  area: string;
  rating: number;
  reviews: number;
  price: number;
  total: number;
  station: string;
  tag: string;
  image: string;
  x: number;
  y: number;
};

export type ItineraryItem = {
  id: string;
  placeId?: string;
  kind: 'place' | 'flight' | 'stay' | 'meal';
  time: string;
  title: string;
  duration: number;
  travelMinutes?: number;
  travelMode?: string;
};

export type ItineraryDay = {
  id: string;
  date: string;
  title: string;
  items: ItineraryItem[];
};

export type VerificationCheck = {
  id: string;
  label: string;
  status: 'pass' | 'warning' | 'conflict' | 'skipped';
  message: string;
};

export type Trip = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  currentStep: StepId;
  completedSteps: StepId[];
  destinationId: string | null;
  startDate: string;
  endDate: string;
  persona: {
    includeFlights: boolean | null;
    includeStays: boolean | null;
    companion: string | null;
    adults: number;
    pace: 'relaxed' | 'balanced' | 'packed';
    interests: string[];
  };
  selectedFlightId: string | null;
  selectedStayId: string | null;
  selectedPlaceIds: string[];
  itinerary: ItineraryDay[] | null;
  verification: VerificationCheck[] | null;
};

export const createTrip = (id: string): Trip => {
  const now = new Date().toISOString();
  return {
    id,
    title: '새 여행',
    createdAt: now,
    updatedAt: now,
    currentStep: 'city',
    completedSteps: [],
    destinationId: null,
    startDate: '',
    endDate: '',
    persona: {
      includeFlights: null,
      includeStays: null,
      companion: null,
      adults: 2,
      pace: 'balanced',
      interests: [],
    },
    selectedFlightId: null,
    selectedStayId: null,
    selectedPlaceIds: [],
    itinerary: null,
    verification: null,
  };
};
