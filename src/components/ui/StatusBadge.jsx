import React from 'react';

const CONFIG = {
  tempus_user: {
    label: 'Tempus User',
    dot: 'bg-success',
    bg: 'bg-bg-tertiary',
    text: 'text-success'
  },
  prospect: {
    label: 'Prospect',
    dot: 'bg-warning',
    bg: 'bg-bg-tertiary',
    text: 'text-warning'
  },
  cold: {
    label: 'No Contact',
    dot: 'bg-text-muted',
    bg: 'bg-bg-tertiary',
    text: 'text-text-secondary'
  }
};

export function StatusBadge({ type }) {
  const cfg = CONFIG[type] ?? CONFIG.cold;

  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 rounded-badge px-2.5 py-1 text-[11px] font-medium',
        cfg.bg,
        cfg.text
      ].join(' ')}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      <span>{cfg.label}</span>
    </span>
  );
}

