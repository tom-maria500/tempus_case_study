import React from 'react';

export function FollowUpChips({ chips, clickable, onSelect }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {chips.map((chip, i) => (
        <button
          key={i}
          type="button"
          onClick={() => clickable && onSelect?.(chip)}
          disabled={!clickable}
          className={[
            'rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
            clickable
              ? 'border-accent-primary text-accent-primary hover:bg-accent-subtle'
              : 'border-bg-border text-text-muted opacity-40'
          ].join(' ')}
        >
          {chip}
        </button>
      ))}
    </div>
  );
}
