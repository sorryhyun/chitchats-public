import { useState, memo } from 'react';
import type { ImageItem } from '../../../types';

interface ImageAttachmentProps {
  // New multi-image prop
  images?: ImageItem[] | null;
  // Legacy single-image props (for backward compatibility)
  imageData?: string | null;
  imageMediaType?: string | null;
  isUserMessage: boolean;
}

export const ImageAttachment = memo(({ images, imageData, imageMediaType, isUserMessage }: ImageAttachmentProps) => {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  // Normalize to array format (support both new and legacy formats)
  const imageList: ImageItem[] = (() => {
    if (images && images.length > 0) {
      return images;
    }
    // Backward compatibility: convert legacy single image to array
    if (imageData && imageMediaType) {
      return [{ data: imageData, media_type: imageMediaType }];
    }
    return [];
  })();

  if (imageList.length === 0) return null;

  const openLightbox = (index: number) => setLightboxIndex(index);
  const closeLightbox = () => setLightboxIndex(null);

  const navigateLightbox = (direction: 'prev' | 'next') => {
    if (lightboxIndex === null) return;
    if (direction === 'prev') {
      setLightboxIndex(lightboxIndex > 0 ? lightboxIndex - 1 : imageList.length - 1);
    } else {
      setLightboxIndex(lightboxIndex < imageList.length - 1 ? lightboxIndex + 1 : 0);
    }
  };

  return (
    <>
      <div className={`mb-2 ${isUserMessage ? 'flex justify-end' : ''}`}>
        {imageList.length === 1 ? (
          // Single image - larger display
          <img
            src={`data:${imageList[0].media_type};base64,${imageList[0].data}`}
            alt="Attached"
            className="max-w-xs max-h-64 rounded-xl border border-slate-200 shadow-sm cursor-pointer hover:opacity-90 transition-opacity"
            loading="lazy"
            onClick={() => openLightbox(0)}
            title="Click to view full size"
          />
        ) : (
          // Multiple images - grid layout
          <div className="grid gap-1.5" style={{
            gridTemplateColumns: imageList.length === 2 ? 'repeat(2, 1fr)' :
                                 imageList.length === 3 ? 'repeat(3, 1fr)' :
                                 'repeat(2, 1fr)',
            maxWidth: imageList.length <= 3 ? '20rem' : '16rem',
          }}>
            {imageList.map((img, index) => (
              <img
                key={index}
                src={`data:${img.media_type};base64,${img.data}`}
                alt={`Attached ${index + 1}`}
                className={`w-full object-cover rounded-lg border border-slate-200 shadow-sm cursor-pointer hover:opacity-90 transition-opacity ${
                  imageList.length <= 2 ? 'h-32' :
                  imageList.length === 3 ? 'h-24' :
                  'h-20'
                }`}
                loading="lazy"
                onClick={() => openLightbox(index)}
                title={`Click to view (${index + 1}/${imageList.length})`}
              />
            ))}
          </div>
        )}
      </div>

      {/* Lightbox Modal with navigation */}
      {lightboxIndex !== null && (
        <div
          className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-4"
          onClick={closeLightbox}
        >
          {/* Close button */}
          <button
            className="absolute top-4 right-4 text-white hover:text-gray-300 transition-colors z-10"
            onClick={closeLightbox}
            aria-label="Close lightbox"
          >
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

          {/* Navigation arrows (only show if multiple images) */}
          {imageList.length > 1 && (
            <>
              <button
                className="absolute left-4 top-1/2 -translate-y-1/2 text-white hover:text-gray-300 transition-colors z-10 p-2"
                onClick={(e) => { e.stopPropagation(); navigateLightbox('prev'); }}
                aria-label="Previous image"
              >
                <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <button
                className="absolute right-4 top-1/2 -translate-y-1/2 text-white hover:text-gray-300 transition-colors z-10 p-2"
                onClick={(e) => { e.stopPropagation(); navigateLightbox('next'); }}
                aria-label="Next image"
              >
                <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </>
          )}

          {/* Image counter */}
          {imageList.length > 1 && (
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-white text-sm bg-black/50 px-3 py-1 rounded-full">
              {lightboxIndex + 1} / {imageList.length}
            </div>
          )}

          {/* Main image */}
          <img
            src={`data:${imageList[lightboxIndex].media_type};base64,${imageList[lightboxIndex].data}`}
            alt="Full size"
            className="max-w-full max-h-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
});
