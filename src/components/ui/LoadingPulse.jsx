import React from 'react';

export function LoadingPulse() {
  return (
    <div className="space-y-3">
      <div className="h-1 w-full rounded-full bg-accent-subtle">
        <div className="h-full w-1/3 rounded-full bg-accent-primary animate-pulse" />
      </div>
      <div className="space-y-3">
        <div className="h-20 rounded-card bg-bg-tertiary animate-pulse" />
        <div className="h-28 rounded-card bg-bg-tertiary animate-pulse" />
        <div className="h-28 rounded-card bg-bg-tertiary animate-pulse" />
      </div>
    </div>
  );
}

