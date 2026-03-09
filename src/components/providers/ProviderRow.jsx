import React from 'react';
import { PriorityBadge } from './PriorityBadge';
import { StatusBadge } from '../ui/StatusBadge';

export function ProviderRow({ provider, onClick, onGenerateBrief }) {
  const {
    rank,
    name,
    institution,
    specialty,
    estimated_annual_patients,
    priority_score,
    last_contact_date,
    current_tempus_user
  } = provider;

  const statusType = current_tempus_user ? 'tempus_user' : 'prospect';
  const isHighPriority = typeof priority_score === 'number' && priority_score >= 8;

  const handleRowClick = () => {
    onClick?.(provider);
  };

  const handleGenerate = (e) => {
    e.stopPropagation();
    onGenerateBrief?.(provider);
  };

  let lastContactLabel = 'No prior contact';
  if (last_contact_date) {
    try {
      const d = new Date(last_contact_date);
      // Guard against "Invalid Date" (some runtimes throw on formatting).
      if (!Number.isNaN(d.getTime())) {
        lastContactLabel = d.toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          year: 'numeric'
        });
      }
    } catch {
      // keep default label
    }
  }

  return (
    <tr
      className={[
        'cursor-pointer border-b border-bg-border bg-bg-secondary text-xs hover:bg-bg-tertiary transition-colors duration-150',
        isHighPriority ? 'border-l-2 border-l-success' : ''
      ].filter(Boolean).join(' ')}
      onClick={handleRowClick}
    >
      <td className="px-3 py-2 font-mono text-[11px] text-text-muted text-right">
        {rank}
      </td>
      <td className="px-3 py-2">
        <div className="flex flex-col">
          <button
            type="button"
            onClick={handleRowClick}
            className="w-max text-xs font-medium text-text-primary hover:text-accent-primary"
          >
            {name}
          </button>
          <span className="mt-0.5 text-[11px] text-text-secondary">
            {institution}
          </span>
        </div>
      </td>
      <td className="px-3 py-2 align-middle">
        <span className="inline-flex rounded-full bg-bg-tertiary px-2 py-0.5 text-[11px] text-text-secondary">
          {specialty}
        </span>
      </td>
      <td className="px-3 py-2 text-right font-mono text-[11px] text-text-primary">
        {estimated_annual_patients?.toLocaleString?.() ?? '—'}
      </td>
      <td className="px-3 py-2">
        <PriorityBadge score={priority_score} />
      </td>
      <td className="px-3 py-2 text-xs text-text-secondary">{lastContactLabel}</td>
      <td className="px-3 py-2">
        <div className="flex items-center justify-end gap-2">
          <StatusBadge type={statusType} />
          <button
            type="button"
            onClick={handleGenerate}
            className="inline-flex items-center rounded-full bg-accent-gradient px-3 py-1.5 text-[11px] font-medium text-bg-primary shadow-tempus transition-transform duration-150 hover:scale-[1.02]"
          >
           Brief →
          </button>
        </div>
      </td>
    </tr>
  );
}

