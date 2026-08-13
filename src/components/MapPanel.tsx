'use client';

import { BedDouble, LocateFixed, Minus, Plus } from 'lucide-react';
import { useState } from 'react';

import { PLACES } from '@/lib/data';
import { getMappablePlaces } from '@/lib/places';
import type { TripPlace } from '@/lib/types';

const MIN_ZOOM = 1;
const MAX_ZOOM = 2.5;
const ZOOM_STEP = 0.25;
const FOCUS_SCALE = 1.35;

export function MapPanel({
  selectedIds = [],
  activeId,
  onMarkerClick,
  showRoute = false,
  stay,
  places = PLACES,
  focusActive = false,
}: {
  selectedIds?: string[];
  activeId?: string | null;
  onMarkerClick?: (id: string) => void;
  showRoute?: boolean;
  stay?: { x: number; y: number } | null;
  places?: TripPlace[];
  /** Smoothly centers the map canvas on the active place without changing map data. */
  focusActive?: boolean;
}) {
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [resetForActiveId, setResetForActiveId] = useState<string | null>(null);
  const placeById = new Map(places.map((place) => [place.id, place]));
  const shown = selectedIds.length
    ? selectedIds.map((id) => placeById.get(id)).filter((place): place is TripPlace => Boolean(place))
    : places;
  const mappable = getMappablePlaces(shown);
  const activePlace = mappable.find((place) => place.id === activeId);
  const shouldFocus = Boolean(focusActive && activePlace && resetForActiveId !== activeId);
  const composedScale = (shouldFocus ? FOCUS_SCALE : 1) * zoom;
  const translateX = activePlace && shouldFocus ? 50 - activePlace.x * composedScale : 0;
  const translateY = activePlace && shouldFocus ? 50 - activePlace.y * composedScale : 0;
  const transform = activePlace && shouldFocus
    ? `translate(${translateX}%, ${translateY}%) scale(${composedScale})`
    : `scale(${zoom})`;

  const zoomIn = () => {
    setResetForActiveId(null);
    setZoom((value) => Math.min(MAX_ZOOM, value + ZOOM_STEP));
  };
  const zoomOut = () => {
    setResetForActiveId(null);
    setZoom((value) => Math.max(MIN_ZOOM, value - ZOOM_STEP));
  };
  const resetView = () => {
    setZoom(MIN_ZOOM);
    setResetForActiveId(activeId ?? null);
  };

  return (
    <div className={`map-panel ${focusActive ? 'map-panel--focusable' : ''}`} aria-label="도쿄 여행 지도 데이터 뷰">
      <div className="map-canvas" style={{ transform }}>
        <div className="map-grid" />
        <div className="map-river map-river--one" />
        <div className="map-river map-river--two" />
        <div className="map-district district-a">SHINJUKU</div>
        <div className="map-district district-b">UENO</div>
        <div className="map-district district-c">GINZA</div>
        {showRoute && mappable.length > 1 && (
          <svg className="route-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            <polyline points={mappable.map((place) => `${place.x},${place.y}`).join(' ')} />
          </svg>
        )}
        {mappable.map((place) => {
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
      <div className="map-controls">
        <button onClick={zoomIn} disabled={zoom >= MAX_ZOOM} aria-label="확대"><Plus size={15} /></button>
        <output aria-live="polite">{zoom.toFixed(2)}×</output>
        <button onClick={zoomOut} disabled={zoom <= MIN_ZOOM} aria-label="축소"><Minus size={15} /></button>
        <button onClick={resetView} disabled={zoom === MIN_ZOOM && (!focusActive || !activePlace || resetForActiveId === activeId)} aria-label="전체 보기"><LocateFixed size={15} /></button>
      </div>
    </div>
  );
}
