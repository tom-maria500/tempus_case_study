import React from 'react';
import { ExternalLink, ArrowRight } from 'lucide-react';

export function IntelCard({ item, onUseInPitch }) {
  return (
    <div className="rounded-card border border-bg-border bg-bg-tertiary p-3 text-sm">
      <div className="font-medium text-text-primary">{item.headline}</div>
      {item.detail && (
        <p className="mt-2 text-xs text-text-secondary">
          <span className="text-text-muted">Detail: </span>
          {item.detail}
        </p>
      )}
      {item.relevance && (
        <p className="mt-1 text-xs text-text-secondary">
          <span className="text-text-muted">Why it matters: </span>
          {item.relevance}
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {item.source_url && (
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-accent-primary hover:underline"
            >
              Source <ExternalLink className="h-3 w-3" />
            </a>
          )}
          {item.date && (
            <span className="text-[11px] text-text-muted">{item.date}</span>
          )}
        </div>
        {onUseInPitch && (
          <button
            type="button"
            onClick={() => onUseInPitch(item.headline)}
            className="inline-flex items-center gap-1 rounded-badge border border-accent-primary/60 px-2 py-1 text-[11px] text-accent-primary transition-colors hover:bg-accent-primary/10"
          >
            Use in Pitch <ArrowRight className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}
