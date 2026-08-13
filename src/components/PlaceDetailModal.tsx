'use client';

import { Clock3, ExternalLink, MapPin, Navigation, Star, X } from 'lucide-react';
import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

export type PlaceDetail = {
  name: string;
  address: string;
  description?: string;
  image?: string;
  category?: string;
  area?: string;
  rating?: number;
  reviewCount?: number;
  duration?: number;
  price?: string;
  priceDescription?: string;
  access?: string;
  badge?: string;
  googleMapsQuery?: string;
};

type PlaceDetailModalProps = {
  place: PlaceDetail | null;
  onClose: () => void;
};

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function PlaceDetailModal({ place, onClose }: PlaceDetailModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!place) return;

    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const focusTimer = window.requestAnimationFrame(() => titleRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;

      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) {
        event.preventDefault();
        titleRef.current?.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === titleRef.current || !dialogRef.current.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !dialogRef.current.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusTimer);
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [place]);

  if (!place) return null;

  const mapQuery = place.googleMapsQuery ?? `${place.name} ${place.address}`;
  const encodedMapQuery = encodeURIComponent(mapQuery);
  const embedUrl = `https://www.google.com/maps?q=${encodedMapQuery}&output=embed`;
  const googleMapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodedMapQuery}`;

  return createPortal(
    <div
      className="place-detail-modal__backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="place-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={place.description ? descriptionId : undefined}
      >
        <header className="place-detail-modal__header">
          <div>
            <span className="eyebrow">PLACE DETAIL</span>
            <h2 id={titleId} ref={titleRef} tabIndex={-1}>{place.name}</h2>
          </div>
          <button className="place-detail-modal__close" onClick={onClose} aria-label="상세보기 닫기">
            <X size={20} />
          </button>
        </header>

        <div className="place-detail-modal__content">
          <section className="place-detail-modal__summary">
            {place.image && <div className="place-detail-modal__image" role="img" aria-label={`${place.name} 전경`} style={{ backgroundImage: `url(${place.image})` }} />}
            <div className="place-detail-modal__information">
              <div className="place-detail-modal__labels">
                {place.badge && <span className="status-badge">{place.badge}</span>}
                {(place.category || place.area) && <span>{[place.category, place.area].filter(Boolean).join(' · ')}</span>}
              </div>
              <p className="place-detail-modal__address"><MapPin size={16} />{place.address}</p>
              {place.description && <p id={descriptionId} className="place-detail-modal__description">{place.description}</p>}

              <dl className="place-detail-modal__facts">
                {typeof place.rating === 'number' && (
                  <div>
                    <dt><Star size={15} /> 평점</dt>
                    <dd>{place.rating.toFixed(1)} <span>({(place.reviewCount ?? 0).toLocaleString()}개 리뷰)</span></dd>
                  </div>
                )}
                {typeof place.duration === 'number' && (
                  <div>
                    <dt><Clock3 size={15} /> 예상 소요시간</dt>
                    <dd>{place.duration < 60 ? `${place.duration}분` : `${Math.floor(place.duration / 60)}시간${place.duration % 60 ? ` ${place.duration % 60}분` : ''}`}</dd>
                  </div>
                )}
                {place.price && (
                  <div>
                    <dt>가격</dt>
                    <dd>{place.price} <span>{place.priceDescription}</span></dd>
                  </div>
                )}
                {place.access && (
                  <div>
                    <dt><Navigation size={15} /> 접근성</dt>
                    <dd>{place.access}</dd>
                  </div>
                )}
              </dl>
            </div>
          </section>

          <section className="place-detail-modal__map-section" aria-labelledby={`${titleId}-map`}>
            <div className="place-detail-modal__map-heading">
              <div>
                <span className="eyebrow">GOOGLE MAPS</span>
                <h3 id={`${titleId}-map`}>위치 및 장소 정보</h3>
                <p>Google Maps에서 주변 위치를 확인하고, 전체 화면에서 리뷰와 사진을 살펴보세요.</p>
              </div>
              <a className="button button--secondary" href={googleMapsUrl} target="_blank" rel="noopener noreferrer">
                지도 · 리뷰 · 사진 보기 <ExternalLink size={15} />
              </a>
            </div>
            <div className="place-detail-modal__map-frame">
              <iframe
                title={`${place.name} Google Maps 위치`}
                src={embedUrl}
                loading="lazy"
                allowFullScreen
                referrerPolicy="no-referrer-when-downgrade"
                tabIndex={-1}
              />
            </div>
          </section>
        </div>
      </div>
    </div>,
    document.body,
  );
}
