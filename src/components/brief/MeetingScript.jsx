import React from 'react';
import { MessageSquare } from 'lucide-react';

export function MeetingScript({ text }) {
  return (
    <section className="rounded-card border border-bg-border bg-bg-secondary p-4 shadow-tempus">
      <header className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded-badge bg-accent-subtle px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.16em] text-accent-primary">
            Meeting Script
          </span>
          <MessageSquare className="h-4 w-4 text-accent-primary" />
        </div>
        <span className="rounded-badge bg-bg-tertiary px-2 py-0.5 text-[10px] text-text-secondary">
          ~30 seconds
        </span>
      </header>
      <p className="text-sm leading-relaxed text-text-primary whitespace-pre-line">
        {text}
      </p>
    </section>
  );
}

