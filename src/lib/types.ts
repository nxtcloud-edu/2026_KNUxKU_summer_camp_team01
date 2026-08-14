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
  placeId?: string;
  name: string;
  nameEn: string;
  country: string;
  flag: string;
  currency: string;
  timezone: string;
  image: string;
  color: string;
  airportCodes: string[];
  source?: 'catalog' | 'google-places';
};

export type PlaceCategory = '명소' | '역사' | '자연' | '미술관' | '맛집' | '쇼핑';

export type TripPlace = {
  id: string;
  name: string;
  localName?: string;
  category: PlaceCategory;
  area: string;
  duration: number;
  rating?: number;
  reviews?: number;
  price?: string;
  summary?: string;
  note?: string;
  image?: string;
  x?: number;
  y?: number;
  closed?: string;
  reservation?: boolean;
  description?: string;
  layer?: string;
  latitude?: number;
  longitude?: number;
  sourceType?: 'google-maps-url' | 'my-maps-file';
  sourceLabel?: string;
  sourceUrl?: string;
  googlePlaceId?: string;
  openingHours?: string[];
  photoReferences?: string[];
};

export type Place = TripPlace & {
  rating: number;
  reviews: number;
  price: string;
  summary: string;
  note: string;
  image: string;
  x: number;
  y: number;
};

export type ImportedPlace = TripPlace & {
  sourceType: 'google-maps-url' | 'my-maps-file';
  sourceLabel: string;
};

export type FlightOffer = {
  id: string;
  originId: string;
  destinationId: string;
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
  type: 'hotel' | 'apartment' | 'hostel' | 'ryokan';
  features: ('central' | 'station' | 'attraction' | 'quiet')[];
  name: string;
  area: string;
  address: string;
  description: string;
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
  originId: string | null;
  destinationId: string | null;
  originLocation: City | null;
  destinationLocation: City | null;
  startDate: string;
  endDate: string;
  persona: {
    includeFlights: boolean | null;
    includeStays: boolean | null;
    companion: string | null;
    adults: number;
    pace: 'relaxed' | 'balanced' | 'packed';
    interests: string[];
    preferredTransportModes: ('walking' | 'publicTransit')[];
    companionDescription: string;
  };
  selectedFlightId: string | null;
  selectedStayId: string | null;
  selectedPlaceIds: string[];
  placeDurations: Record<string, number>;
  importedPlaces: Record<string, ImportedPlace>;
  itinerary: ItineraryDay[] | null;
  verification: VerificationCheck[] | null;
  /** The exact itinerary that the current AI verification result was generated from. */
  verifiedItinerary: ItineraryDay[] | null;
  /** Set only after the verified itinerary has been explicitly saved. */
  savedAt: string | null;
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
    originId: null,
    destinationId: null,
    originLocation: null,
    destinationLocation: null,
    startDate: '',
    endDate: '',
    persona: {
      includeFlights: null,
      includeStays: null,
      companion: null,
      adults: 2,
      pace: 'balanced',
      interests: [],
      preferredTransportModes: [],
      companionDescription: '',
    },
    selectedFlightId: null,
    selectedStayId: null,
    selectedPlaceIds: [],
    placeDurations: {},
    importedPlaces: {},
    itinerary: null,
    verification: null,
    verifiedItinerary: null,
    savedAt: null,
  };
};
