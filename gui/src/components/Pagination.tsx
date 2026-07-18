interface PaginationProps {
  currentPage: number;
  totalPages: number;
  previousDisabled: boolean;
  nextDisabled: boolean;
  onPrevious: () => void;
  onNext: () => void;
}

export function Pagination({
  currentPage,
  totalPages,
  previousDisabled,
  nextDisabled,
  onPrevious,
  onNext,
}: PaginationProps) {
  return (
    <div className="flex items-center justify-between p-4 border-t border-[var(--color-border)]">
      <div className="text-sm text-[var(--color-text-muted)]">
        Page {currentPage} of {totalPages}
      </div>
      <div className="flex gap-2">
        <button
          onClick={onPrevious}
          disabled={previousDisabled}
          className="px-3 py-1 rounded text-sm bg-[var(--color-bg-tertiary)] text-[var(--color-text)] disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--color-border)] transition-colors"
        >
          Previous
        </button>
        <button
          onClick={onNext}
          disabled={nextDisabled}
          className="px-3 py-1 rounded text-sm bg-[var(--color-bg-tertiary)] text-[var(--color-text)] disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--color-border)] transition-colors"
        >
          Next
        </button>
      </div>
    </div>
  );
}
