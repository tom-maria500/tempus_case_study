import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

export function KBCitations({ chunks = [] }) {
  const [open, setOpen] = useState(false);

  if (!chunks || chunks.length === 0) return null;

  return (
    <section className="mt-3 rounded-card border border-bg-border bg-bg-secondary p-3 shadow-tempus">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left text-xs text-text-secondary"
      >
        <span>
          View KB Sources{' '}
          <span className="text-text-muted">({chunks.length} chunks)</span>
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-text-muted" />
        ) : (
          <ChevronRight className="h-4 w-4 text-text-muted" />
        )}
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {chunks.map((chunk, idx) => (
            <div
              key={idx}
              className="border-l-2 border-accent-primary bg-[#0A0E1A] px-3 py-2 rounded-r-card text-[11px] font-mono text-text-secondary"
            >
              <div className="mb-1 text-[10px] uppercase tracking-[0.16em] text-text-muted">
                Source {idx + 1}
              </div>
              <pre className="whitespace-pre-wrap break-words">
                {chunk}
              </pre>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

