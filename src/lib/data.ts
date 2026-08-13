import type { City, FlightOffer, Place, StayOffer, VerificationCheck } from '@/lib/types';

export const ORIGIN_CITIES: City[] = [
  { id: 'seoul', name: '서울', nameEn: 'Seoul', country: '대한민국', flag: '🇰🇷', currency: 'KRW', timezone: 'GMT+9', image: 'https://picsum.photos/seed/voyagent-seoul/1200/630', color: '#4f6bc7', airportCodes: ['ICN', 'GMP'] },
  { id: 'busan', name: '부산', nameEn: 'Busan', country: '대한민국', flag: '🇰🇷', currency: 'KRW', timezone: 'GMT+9', image: 'https://picsum.photos/seed/voyagent-busan/1200/630', color: '#397f91', airportCodes: ['PUS'] },
  { id: 'jeju', name: '제주', nameEn: 'Jeju', country: '대한민국', flag: '🇰🇷', currency: 'KRW', timezone: 'GMT+9', image: 'https://picsum.photos/seed/voyagent-jeju/1200/630', color: '#b26a43', airportCodes: ['CJU'] },
];

export const CITIES: City[] = [
  { id: 'tokyo', name: '도쿄', nameEn: 'Tokyo', country: '일본', flag: '🇯🇵', currency: 'JPY', timezone: 'GMT+9', image: 'https://picsum.photos/seed/voyagent-tokyo/1200/630', color: '#6173c9', airportCodes: ['NRT', 'HND'] },
  { id: 'osaka', name: '오사카', nameEn: 'Osaka', country: '일본', flag: '🇯🇵', currency: 'JPY', timezone: 'GMT+9', image: 'https://picsum.photos/seed/voyagent-osaka/1200/630', color: '#b66c52', airportCodes: ['KIX'] },
  { id: 'paris', name: '파리', nameEn: 'Paris', country: '프랑스', flag: '🇫🇷', currency: 'EUR', timezone: 'GMT+2', image: 'https://picsum.photos/seed/voyagent-paris/1200/630', color: '#3f8a7d', airportCodes: ['CDG'] },
  { id: 'bangkok', name: '방콕', nameEn: 'Bangkok', country: '태국', flag: '🇹🇭', currency: 'THB', timezone: 'GMT+7', image: 'https://picsum.photos/seed/voyagent-bangkok/1200/630', color: '#915a91', airportCodes: ['BKK'] },
];

export const PLACES: Place[] = [
  { id: 'sensoji', name: '센소지', localName: '浅草寺', category: '역사', area: '아사쿠사', rating: 4.5, reviews: 32841, duration: 90, price: '무료', summary: '628년에 창건된 도쿄에서 가장 오래된 사찰. 가미나리몬과 나카미세 상점가가 이어집니다.', note: '이른 아침에 방문하면 한적하게 둘러볼 수 있어요.', image: 'https://picsum.photos/seed/sensoji/480/360', x: 76, y: 29 },
  { id: 'skytree', name: '도쿄 스카이트리', category: '명소', area: '오시아게', rating: 4.4, reviews: 58120, duration: 120, price: '2,100엔', summary: '도쿄 전경을 한눈에 볼 수 있는 634m 높이의 전망대입니다.', note: '해 질 무렵 방문하면 낮과 야경을 함께 볼 수 있어요.', image: 'https://picsum.photos/seed/skytree/480/360', x: 84, y: 33, reservation: true },
  { id: 'museum', name: '도쿄 국립박물관', category: '미술관', area: '우에노', rating: 4.6, reviews: 21004, duration: 150, price: '1,000엔', summary: '일본 최대 규모의 박물관으로 국보와 동아시아 미술품을 전시합니다.', note: '상설관만 보아도 두 시간 이상 필요해요.', image: 'https://picsum.photos/seed/tokyo-museum/480/360', x: 67, y: 24, closed: '월 휴관' },
  { id: 'meiji', name: '메이지 신궁', category: '역사', area: '하라주쿠', rating: 4.6, reviews: 40122, duration: 90, price: '무료', summary: '도심 한가운데 울창한 숲길을 지나 만나는 고요한 신궁입니다.', note: '오전 산책 코스로 배치하면 이동이 편해요.', image: 'https://picsum.photos/seed/meiji/480/360', x: 34, y: 46 },
  { id: 'shibuya', name: '시부야 스카이', category: '명소', area: '시부야', rating: 4.7, reviews: 18940, duration: 90, price: '2,200엔', summary: '시부야 교차로와 도쿄 도심을 내려다보는 개방형 전망 시설입니다.', note: '인기 시간대는 사전 예약을 권해요.', image: 'https://picsum.photos/seed/shibuya-sky/480/360', x: 31, y: 58, reservation: true },
  { id: 'shinjuku', name: '신주쿠 교엔', category: '자연', area: '신주쿠', rating: 4.6, reviews: 19871, duration: 120, price: '500엔', summary: '일본식·영국식·프랑스식 정원이 어우러진 넓은 도심 공원입니다.', note: '여행 중간에 여유를 더하기 좋은 장소예요.', image: 'https://picsum.photos/seed/shinjuku-gyoen/480/360', x: 38, y: 36, closed: '월 휴관' },
  { id: 'teamlab', name: '팀랩 플래닛', category: '미술관', area: '도요스', rating: 4.5, reviews: 35220, duration: 150, price: '3,800엔', summary: '물과 빛, 거대한 설치 작품을 몸으로 경험하는 몰입형 미술관입니다.', note: '날짜 지정 예약이 필요해 준비물에 추가할게요.', image: 'https://picsum.photos/seed/teamlab/480/360', x: 69, y: 72, reservation: true },
  { id: 'tsukiji', name: '츠키지 장외시장', category: '맛집', area: '츠키지', rating: 4.3, reviews: 29510, duration: 90, price: '약 3,000엔', summary: '초밥과 해산물 덮밥, 계란말이 등 다양한 길거리 음식을 맛볼 수 있습니다.', note: '오전 10시 전에 가면 대기 시간을 줄일 수 있어요.', image: 'https://picsum.photos/seed/tsukiji/480/360', x: 61, y: 63 },
  { id: 'ginza', name: '긴자 식스', category: '쇼핑', area: '긴자', rating: 4.2, reviews: 12884, duration: 120, price: '무료', summary: '패션과 라이프스타일 브랜드, 예술 설치가 함께 있는 복합 쇼핑 공간입니다.', note: '비 오는 날 대안으로 좋아요.', image: 'https://picsum.photos/seed/ginza-six/480/360', x: 57, y: 54 },
];

export const FLIGHTS: FlightOffer[] = [
  { id: 'ke703', originId: 'seoul', destinationId: 'tokyo', airline: '대한항공', code: 'KE703', price: 684000, outbound: '09:05 ICN → 11:20 NRT', inbound: '14:30 NRT → 17:00 ICN', duration: '2시간 15분', tag: '추천', note: '오전 도착이라 첫날 일정을 넉넉하게 쓸 수 있어요.' },
  { id: 'lj201', originId: 'seoul', destinationId: 'tokyo', airline: '진에어', code: 'LJ201', price: 412000, outbound: '09:35 ICN → 12:05 NRT', inbound: '18:40 NRT → 21:15 ICN', duration: '2시간 30분', tag: '최저가', note: '가격을 아끼고 현지 활동에 예산을 더 쓸 수 있어요.' },
  { id: 'nh6970', originId: 'seoul', destinationId: 'tokyo', airline: '전일본공수', code: 'NH6970', price: 736000, outbound: '07:50 ICN → 10:00 HND', inbound: '19:00 HND → 21:25 ICN', duration: '2시간 10분', tag: '최단시간', note: '하네다 도착이라 도심 이동 시간이 가장 짧아요.' },
];

export const STAYS: StayOffer[] = [
  { id: 'gracery', type: 'hotel', features: ['central', 'station', 'attraction'], name: '호텔 그레이스리 신주쿠', area: '신주쿠', rating: 8.7, reviews: 2431, price: 180000, total: 720000, station: '신주쿠역 도보 6분', tag: '위치 최고', image: 'https://picsum.photos/seed/gracery/640/420', x: 39, y: 37 },
  { id: 'granbell', type: 'hotel', features: ['station', 'quiet'], name: '신주쿠 그란벨 호텔', area: '신주쿠', rating: 8.2, reviews: 1180, price: 112000, total: 448000, station: '신주쿠산초메역 도보 4분', tag: '가성비', image: 'https://picsum.photos/seed/granbell/640/420', x: 43, y: 40 },
  { id: 'park-hyatt', type: 'hotel', features: ['central', 'quiet'], name: '파크 하이엇 도쿄', area: '니시신주쿠', rating: 9.2, reviews: 3902, price: 480000, total: 1920000, station: '도초마에역 도보 8분', tag: '평점 높음', image: 'https://picsum.photos/seed/park-hyatt/640/420', x: 34, y: 34 },
];

export const VERIFICATION_CHECKS: VerificationCheck[] = [
  { id: 'V1', label: '영업시간 · 휴관일', status: 'conflict', message: '월요일 휴관 장소 1곳을 다른 날로 옮겨야 해요.' },
  { id: 'V2', label: '이동 시간 실현성', status: 'warning', message: 'Day 2 마지막 이동에 여유가 조금 부족해요.' },
  { id: 'V3', label: '항공 도착 · 출발 여유', status: 'pass', message: '공항 이동 시간을 충분히 확보했어요.' },
  { id: 'V4', label: '숙소 체크인 · 체크아웃', status: 'pass', message: '체크인과 체크아웃 시간이 적절해요.' },
  { id: 'V5', label: '하루 일정량', status: 'warning', message: 'Day 3 활동 시간이 10시간을 넘어요.' },
  { id: 'V6', label: '예산', status: 'pass', message: '설정한 예산 범위 안이에요.' },
  { id: 'V7', label: '접근성', status: 'pass', message: '요청한 이동 조건을 충족해요.' },
  { id: 'V8', label: '관심사 반영', status: 'pass', message: '선택한 관심사가 일정에 고르게 반영됐어요.' },
  { id: 'V9', label: '사전 예약 필요', status: 'warning', message: '예약이 필요한 장소 2곳이 있어요.' },
  { id: 'V10', label: '시즌 · 날씨', status: 'pass', message: '실내 대안이 포함되어 있어요.' },
];

export const INTERESTS = ['맛집', '카페·디저트', '자연·공원', '미술관·박물관', '역사·문화', '쇼핑', '야경', '액티비티', '사진 스팟', '휴양·온천'];
