'use client';

import { BedDouble, LocateFixed, Minus, Plus } from 'lucide-react';

import { PLACES } from '@/lib/data';

export function MapPanel({ selectedIds = [], activeId, onMarkerClick, showRoute = false, stay, focusActive = false }: {
  selectedIds?: string[];
  activeId?: string | null;
  onMarkerClick?: (id: string) => void;
  showRoute?: boolean;
  stay?: { x: number; y: number } | null;
  /** Smoothly centers the map canvas on the active place without changing map data. */
  focusActive?: boolean;
}) {
  const shown = selectedIds.length
    ? selectedIds.map((id) => PLACES.find((place) => place.id === id)).filter((place): place is (typeof PLACES)[number] => Boolean(place))
    : PLACES;
  const activePlace = PLACES.find((place) => place.id === activeId);
  const focusStyle = focusActive && activePlace
    ? { transform: `translate(${50 - activePlace.x * 1.35}%, ${50 - activePlace.y * 1.35}%) scale(1.35)` }
    : undefined;

  return (
    <div className={`map-panel ${focusActive ? 'map-panel--focusable' : ''}`} aria-label="도쿄 여행 지도 데이터 뷰">
      <div className="map-canvas" style={focusStyle}>
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
      </div>
      <div className="map-legend"><span><i className="legend-selected" /> 선택</span><span><i /> 후보</span>{stay && <span><BedDouble size={12} /> 숙소</span>}</div>
      <div className="map-controls"><button aria-label="확대"><Plus size={15} /></button><button aria-label="축소"><Minus size={15} /></button><button aria-label="전체 보기"><LocateFixed size={15} /></button></div>
    </div>
  );
}
