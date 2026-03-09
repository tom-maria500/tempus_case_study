import React from 'react';
import { Search } from 'lucide-react';

export function EmptyState({ title = 'No providers found', description }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-bg-border bg-bg-secondary/60 px-6 py-10 text-center">
      <div className="mb-3 rounded-full bg-bg-tertiary p-3">
        <Search className="h-5 w-5 text-text-secondary" />
      </div>
      <h3 className="text-sm font-medium text-text-primary">{title}</h3>
      {description && (
        <p className="mt-2 max-w-md text-xs text-text-secondary">
          {description}
        </p>
      )}
    </div>
  );
}

