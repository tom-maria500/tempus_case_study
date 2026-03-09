import React from 'react';
import { Shield } from 'lucide-react';

export function ObjectionHandler({ objection, response }) {
  return (
    <section className="rounded-card border border-bg-border bg-bg-secondary p-4 shadow-tempus">
      <header className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded-badge bg-warning/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.16em] text-warning">
            Objection Handler
          </span>
          <Shield className="h-4 w-4 text-warning" />
        </div>
      </header>
      {objection && (
        <p className="mb-2 text-xs italic text-text-secondary">
          Concern: {objection}
        </p>
      )}
      <p className="text-sm leading-relaxed text-text-primary whitespace-pre-line">
        {response}
      </p>
    </section>
  );
}

