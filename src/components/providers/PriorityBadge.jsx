import React, { useEffect, useState } from 'react';

export function PriorityBadge({ score }) {
  const [width, setWidth] = useState(0);
  const safeScore = typeof score === 'number' ? score : 0;
  const pct = Math.max(0, Math.min(10, safeScore)) * 10;

  let colorClass = 'bg-priority-low text-priority-low';
  let barClass = 'bg-priority-low';
  if (safeScore >= 8) {
    colorClass = 'text-success';
    barClass = 'bg-success';
  } else if (safeScore >= 5) {
    colorClass = 'bg-priority-mid text-priority-mid';
    barClass = 'bg-priority-mid';
  }

  useEffect(() => {
    const id = setTimeout(() => setWidth(pct), 50);
    return () => clearTimeout(id);
  }, [pct]);

  return (
    <div className="flex items-center gap-2">
      <span
        className={[
          'min-w-[2.5rem] text-right text-xs font-medium font-mono',
          colorClass.replace('bg-', 'text-')
        ].join(' ')}
      >
        {safeScore?.toFixed(1) ?? '--'}
      </span>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-bg-tertiary">
        <div
          className={`h-full rounded-full transition-[width] duration-400 ease-out ${barClass}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

