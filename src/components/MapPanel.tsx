'use client';

import { GoogleMap, MarkerF, OverlayViewF, PolylineF, useJsApiLoader } from '@react-google-maps/api';
import { BedDouble, LocateFixed, MapPinOff } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { PLACES } from '@/lib/data';
import { getMappablePlaces } from '@/lib/places';
import type { StayOffer, TripPlace } from '@/lib/types';

const GOOGLE_MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? '';
const SCRIPT_ID = 'voyagent-google-maps-script';

const TOKYO_CENTER = { lat: 35.6812, lng: 139.7671 };
const OVERVIEW_ZOOM = 12;
const FOCUS_ZOOM = 16;
const SINGLE_POINT_ZOOM = 14;

const MARKER_FILL = '#4f46e5';
const MARKER_STROKE = '#ffffff';
const CANDIDATE_FILL = '#ffffff';
const CANDIDATE_STROKE = '#ef4444';
const STAY_FILL = '#52525b';

const MAP_OPTIONS: google.maps.MapOptions = {
  disableDefaultUI: false,
  zoomControl: true,
  streetViewControl: false,
  mapTypeControl: false,
  fullscreenControl: false,
  clickableIcons: false,
};

type StayMarker = Pick<StayOffer, 'latitude' | 'longitude'> & { id?: string; name?: string };

/** Moves the camera smoothly when the browser/API supports moveCamera(), otherwise falls back to an instant pan + zoom. */
function animateCamera(map: google.maps.Map, center: google.maps.LatLngLiteral, zoom: number) {
  const withMoveCamera = map as google.maps.Map & { moveCamera?: (options: { center: google.maps.LatLngLiteral; zoom: number }) => void };
  if (typeof withMoveCamera.moveCamera === 'function') {
    withMoveCamera.moveCamera({ center, zoom });
    return;
  }
  map.panTo(center);
  map.setZoom(zoom);
}

export function MapPanel({
  selectedIds = [],
  activeId,
  onMarkerClick,
  showRoute = false,
  stay,
  places = PLACES,
  focusActive = false,
  showInfoWindow = true,
}: {
  selectedIds?: string[];
  activeId?: string | null;
  onMarkerClick?: (id: string) => void;
  showRoute?: boolean;
  stay?: StayMarker | null;
  places?: TripPlace[];
  /** Smoothly pans/zooms the map onto the active place instead of leaving the camera static. */
  focusActive?: boolean;
  /** Set to false when the caller already shows place details elsewhere (e.g. a presentation drawer). */
  showInfoWindow?: boolean;
}) {
  const { isLoaded, loadError } = useJsApiLoader({ id: SCRIPT_ID, googleMapsApiKey: GOOGLE_MAPS_API_KEY });
  const [map, setMap] = useState<google.maps.Map | null>(null);

  const placeById = new Map(places.map((place) => [place.id, place]));
  const shown = selectedIds.length
    ? selectedIds.map((id) => placeById.get(id)).filter((place): place is TripPlace => Boolean(place))
    : places;
  const mappable = getMappablePlaces(shown);
  const activePlace = mappable.find((place) => place.id === activeId);
  const activeStay = !activePlace && stay && stay.id != null && stay.id === activeId ? stay : null;

  const boundsKey = useMemo(
    () => [...mappable.map((place) => place.id), stay ? `stay:${stay.latitude}:${stay.longitude}` : ''].join('|'),
    [mappable, stay],
  );

  const fitToMarkers = useCallback((instance: google.maps.Map, targetMappable: TripPlace[], targetStay?: StayMarker | null) => {
    const points = [
      ...getMappablePlaces(targetMappable).map((place) => ({ lat: place.latitude, lng: place.longitude })),
      ...(targetStay ? [{ lat: targetStay.latitude, lng: targetStay.longitude }] : []),
    ];
    if (points.length === 0) {
      instance.setCenter(TOKYO_CENTER);
      instance.setZoom(OVERVIEW_ZOOM);
      return;
    }
    if (points.length === 1) {
      instance.setCenter(points[0]);
      instance.setZoom(SINGLE_POINT_ZOOM);
      return;
    }
    const bounds = new google.maps.LatLngBounds();
    points.forEach((point) => bounds.extend(point));
    instance.fitBounds(bounds, 56);
  }, []);

  // Fit the camera to the current marker set whenever the *set itself* changes (not on every render),
  // so a user's manual zoom/pan isn't reset by unrelated re-renders.
  useEffect(() => {
    if (!map) return;
    if (focusActive && activeId) return;
    fitToMarkers(map, mappable, stay ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, boundsKey]);

  // Hover/click-focus: smoothly zoom onto the active place or stay, and zoom back out when focus ends.
  useEffect(() => {
    if (!map || !focusActive) return;
    if (activePlace) {
      animateCamera(map, { lat: activePlace.latitude, lng: activePlace.longitude }, FOCUS_ZOOM);
    } else if (activeStay) {
      animateCamera(map, { lat: activeStay.latitude, lng: activeStay.longitude }, FOCUS_ZOOM);
    } else {
      fitToMarkers(map, mappable, stay ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, activeId, focusActive]);

  const handleLoad = (instance: google.maps.Map) => {
    setMap(instance);
    fitToMarkers(instance, mappable, stay ?? null);
  };

  const resetView = () => {
    if (map) fitToMarkers(map, mappable, stay ?? null);
  };

  const selectedMarkerIcon = useCallback((label: string, active: boolean): google.maps.Icon => {
    const size = active ? 34 : 28;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 28 28">`
      + `<circle cx="14" cy="14" r="12" fill="${MARKER_FILL}" stroke="${MARKER_STROKE}" stroke-width="${active ? 3 : 2}"/>`
      + `<text x="14" y="18.5" font-size="12" font-weight="700" font-family="system-ui, sans-serif" text-anchor="middle" fill="#ffffff">${label}</text>`
      + '</svg>';
    return {
      url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
      scaledSize: new google.maps.Size(size, size),
      anchor: new google.maps.Point(size / 2, size / 2),
    };
  }, []);

  const candidateMarkerIcon = useCallback((active: boolean): google.maps.Icon => {
    const size = active ? 20 : 14;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 14 14">`
      + `<circle cx="7" cy="7" r="5.5" fill="${CANDIDATE_FILL}" stroke="${active ? MARKER_FILL : CANDIDATE_STROKE}" stroke-width="2"/>`
      + '</svg>';
    return {
      url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
      scaledSize: new google.maps.Size(size, size),
      anchor: new google.maps.Point(size / 2, size / 2),
    };
  }, []);

  const stayMarkerIcon = useMemo((): google.maps.Icon | undefined => {
    if (!isLoaded) return undefined;
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 26 26">'
      + `<rect x="1" y="1" width="24" height="24" rx="6" fill="${STAY_FILL}" stroke="#ffffff" stroke-width="2"/>`
      + '<path d="M7 17v-6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v6" stroke="#ffffff" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
      + '<path d="M7 15h12" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round"/>'
      + '<path d="M7 15v3M19 15v3" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round"/>'
      + '</svg>';
    return {
      url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
      scaledSize: new google.maps.Size(26, 26),
      anchor: new google.maps.Point(13, 13),
    };
  }, [isLoaded]);

  if (!GOOGLE_MAPS_API_KEY || loadError) {
    return (
      <div className={`map-panel map-panel--fallback ${focusActive ? 'map-panel--focusable' : ''}`} aria-label="도쿄 여행 지도">
        <MapPinOff size={26} />
        <strong>지도를 표시할 수 없어요</strong>
        <span>{loadError ? 'Google Maps를 불러오지 못했어요.' : 'Google Maps API 키가 설정되지 않았어요.'}</span>
      </div>
    );
  }

  if (!isLoaded) {
    return <div className={`map-panel map-panel--loading ${focusActive ? 'map-panel--focusable' : ''}`} aria-label="도쿄 여행 지도를 불러오는 중" />;
  }

  return (
    <div className={`map-panel ${focusActive ? 'map-panel--focusable' : ''}`} aria-label="도쿄 여행 지도">
      <GoogleMap
        mapContainerClassName="map-panel__canvas"
        center={TOKYO_CENTER}
        zoom={OVERVIEW_ZOOM}
        options={MAP_OPTIONS}
        onLoad={handleLoad}
        onUnmount={() => setMap(null)}
      >
        {showRoute && mappable.length > 1 && (
          <PolylineF
            path={mappable.map((place) => ({ lat: place.latitude, lng: place.longitude }))}
            options={{ strokeColor: MARKER_FILL, strokeOpacity: 0.85, strokeWeight: 3, geodesic: true }}
          />
        )}
        {mappable.map((place) => {
          const selectedIndex = selectedIds.indexOf(place.id);
          const selected = selectedIndex >= 0;
          const active = activeId === place.id;
          return (
            <MarkerF
              key={place.id}
              position={{ lat: place.latitude, lng: place.longitude }}
              icon={selected ? selectedMarkerIcon(String(selectedIndex + 1), active) : candidateMarkerIcon(active)}
              zIndex={active ? 20 : selected ? 10 : 1}
              onClick={() => onMarkerClick?.(place.id)}
              onMouseOver={() => onMarkerClick?.(place.id)}
              title={place.name}
            >
              {active && showInfoWindow && (
                <OverlayViewF
                  position={{ lat: place.latitude, lng: place.longitude }}
                  mapPaneName="floatPane"
                  getPixelPositionOffset={() => ({ x: 0, y: -14 })}
                >
                  <div className="marker-popover"><strong>{place.name}</strong><small>{place.category} · {place.area}</small></div>
                </OverlayViewF>
              )}
            </MarkerF>
          );
        })}
        {stay && stayMarkerIcon && (
          <MarkerF
            position={{ lat: stay.latitude, lng: stay.longitude }}
            icon={stayMarkerIcon}
            zIndex={15}
            title={stay.name ?? '숙소'}
            onClick={stay.id ? () => onMarkerClick?.(stay.id!) : undefined}
          />
        )}
      </GoogleMap>
      <div className="map-legend"><span><i className="legend-selected" /> 선택</span><span><i className="legend-candidate" /> 후보</span>{stay && <span><BedDouble size={12} /> 숙소</span>}</div>
      <div className="map-controls">
        <button onClick={resetView} aria-label="전체 보기"><LocateFixed size={15} /></button>
      </div>
    </div>
  );
}
