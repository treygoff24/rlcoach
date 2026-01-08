// frontend/src/components/layout/UploadModal.tsx
'use client';

import { useEffect, useRef } from 'react';
import { UploadDropzone } from '@/components/UploadDropzone';

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadComplete?: (uploadId: string) => void;
}

export function UploadModal({ isOpen, onClose, onUploadComplete }: UploadModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Focus trap and keyboard handling
  useEffect(() => {
    if (!isOpen) return;

    // Focus close button when modal opens
    closeButtonRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      // Focus trap
      if (e.key === 'Tab' && modalRef.current) {
        const focusableElements = modalRef.current.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const firstElement = focusableElements[0] as HTMLElement;
        const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

        if (e.shiftKey && document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        } else if (!e.shiftKey && document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    // Prevent body scroll when modal is open
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop with blur */}
      <div
        className="fixed inset-0 bg-void/80 backdrop-blur-md z-50 animate-fade-in"
        aria-hidden="true"
      />

      {/* Modal positioning wrapper - clicking outside modal closes it */}
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-modal-title"
        onClick={onClose}
      >
        <div
          ref={modalRef}
          className="relative w-full max-w-2xl animate-scale-in"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Glow effects */}
          <div className="absolute -inset-1 bg-gradient-to-r from-fire/20 via-boost/20 to-fire/20 rounded-3xl blur-xl opacity-50" />

          {/* Modal content */}
          <div className="relative glass-elevated rounded-3xl overflow-hidden">
            {/* Gradient border */}
            <div className="absolute inset-0 glow-border rounded-3xl pointer-events-none" />

            {/* Header */}
            <div className="relative flex items-center justify-between p-6 border-b border-white/5">
              <div className="flex items-center gap-4">
                {/* Upload icon with glow */}
                <div className="relative">
                  <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-fire to-fire-600 flex items-center justify-center shadow-glow-fire">
                    <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                  </div>
                  <div className="absolute inset-0 rounded-2xl animate-pulse-ring border-2 border-fire/50" />
                </div>
                <div>
                  <h2 id="upload-modal-title" className="text-xl font-display text-white tracking-wide">
                    UPLOAD REPLAYS
                  </h2>
                  <p className="text-sm text-white/50 mt-0.5">
                    Drop your .replay files to analyze gameplay
                  </p>
                </div>
              </div>

              {/* Close button */}
              <button
                ref={closeButtonRef}
                onClick={onClose}
                aria-label="Close upload modal"
                className="p-3 text-white/50 hover:text-white hover:bg-white/5 rounded-xl transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-boost"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Content */}
            <div className="relative p-6 overflow-y-auto max-h-[60vh]">
              {/* Decorative grid pattern */}
              <div className="absolute inset-0 bg-grid-pattern bg-grid opacity-20 pointer-events-none" />

              <UploadDropzone onUploadComplete={onUploadComplete} />
            </div>

            {/* Footer with tips */}
            <div className="relative px-6 py-4 border-t border-white/5 bg-white/[0.02]">
              <div className="flex items-center gap-3 text-xs text-white/40">
                <svg className="w-4 h-4 text-boost" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>
                  Replays are processed securely and analyzed within minutes
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
