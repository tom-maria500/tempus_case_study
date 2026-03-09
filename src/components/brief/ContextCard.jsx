import React from 'react';
import { TrendingUp } from 'lucide-react';

export function ContextCard({ physician, priorityRationale }) {
  if (!physician) return null;

  const {
    specialty,
    institution,
    city,
    state,
    estimated_annual_patients,
    primary_cancer_focus,
    last_contact_date
  } = physician;

  const lastContact = last_contact_date
    ? new Date(last_contact_date).toLocaleDateString()
    : 'No prior contact';

  const focusArea = (primary_cancer_focus || '').toString().trim();
  const rationale = priorityRationale?.trim?.();

  return (
    <section className="rounded-card border border-bg-border bg-bg-secondary p-4 shadow-tempus">
      <header className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded-badge bg-info/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.16em] text-info">
            Priority Rationale
          </span>
          <TrendingUp className="h-4 w-4 text-info" />
        </div>
      </header>
      <div className="space-y-2 text-sm text-text-primary">
        <p>
          <span className="font-medium text-text-secondary">Focus area: </span>
          {focusArea || 'Not specified'}
        </p>
        {rationale && (
          <p className="leading-relaxed">{rationale}</p>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-text-secondary">
        <div className="rounded-card bg-bg-tertiary px-3 py-1.5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted">
            Est. Patients
          </div>
          <div className="mt-1 font-mono text-xs text-text-primary">
            {estimated_annual_patients?.toLocaleString?.() ?? '—'}
          </div>
        </div>
        <div className="rounded-card bg-bg-tertiary px-3 py-1.5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted">
            Last Contact
          </div>
          <div className="mt-1 text-xs text-text-primary">{lastContact}</div>
        </div>
        <div className="rounded-card bg-bg-tertiary px-3 py-1.5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted">
            Location
          </div>
          <div className="mt-1 text-xs text-text-primary">
            {institution} · {city}, {state}
          </div>
        </div>
        <div className="rounded-card bg-bg-tertiary px-3 py-1.5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted">
            Specialty
          </div>
          <div className="mt-1 text-xs text-text-primary">{specialty}</div>
        </div>
      </div>
    </section>
  );
}

