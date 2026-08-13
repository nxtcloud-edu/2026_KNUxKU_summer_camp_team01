'use client';

import { BedDouble, LocateFixed, Minus, Plus } from 'lucide-react';

import { PLACES } from '@/lib/data';

export function MapPanel({ selectedIds = [], activeId, onMarkerClick, showRoute = false, stay }: {
  selectedIds?: string[];
  activeId?: string | null;
  onMarkerClick?: (id: string) => void;
  showRoute?: boolean;
  stay?: { x: number; y: number } | null;
}) {
  const shown = selectedIds.length ? PLACES.filter((place) => selectedIds.includes(place.id)) : PLACES;
  return (
    <div className="map-panel" aria-label="도쿄 여행 지도 데이터 뷰">
      <div className="map-grid" />
      <div className="map-river map-river--one" />
      <div className="map-river map-river--two" />
      <div className="map-district district-a">SHINJUKU</div>
      <div className="map-district district-b">UENO</div>
      <div className="map-district district-c">GINZA</div>
      {showRoute && shown.length > 1 && (
        <svg className="route-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
          <polyline points={shown.map((place) => `${place.x},${place.y}`).join(' ')} />
        </svg>
      )}
      {shown.map((place) => {
        const selectedIndex = selectedIds.indexOf(place.id);
        const selected = selectedIndex >= 0;
        return (
          <button
            key={place.id}
            className={`map-marker ${selected ? 'is-selected' : ''} ${activeId === place.id ? 'is-active' : ''}`}
            style={{ left: `${place.x}%`, top: `${place.y}%` }}
            onClick={() => onMarkerClick?.(place.id)}
            aria-label={`${place.name}${selected ? ', 선택됨' : ''}`}
          >
            {selected ? selectedIndex + 1 : <span />}
            {activeId === place.id && <span className="marker-popover"><strong>{place.name}</strong><small>{place.category} · {place.area}</small></span>}
          </button>
        );
      })}
      {stay && <div className="stay-marker" style={{ left: `${stay.x}%`, top: `${stay.y}%` }}><BedDouble size={13} /></div>}
      <div className="map-legend"><span><i className="legend-selected" /> 선택</span><span><i /> 후보</span>{stay && <span><BedDouble size={12} /> 숙소</span>}</div>
      <div className="map-controls"><button aria-label="확대"><Plus size={15} /></button><button aria-label="축소"><Minus size={15} /></button><button aria-label="전체 보기"><LocateFixed size={15} /></button></div>
    </div>
  );
}
