import React from 'react';
import { Search } from 'lucide-react';
import { SearchBar } from '../ui/SearchBar';

export function TopBar({ title, subtitle, onSearch }) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-bg-border bg-bg-primary/60 px-6 py-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text-primary">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1 text-xs text-text-secondary">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="w-80 max-w-xs">
          <SearchBar
            icon={Search}
            placeholder="Search physician name or territory..."
            onChange={onSearch}
          />
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-bg-tertiary text-xs font-medium text-text-secondary">
          MK
        </div>
      </div>
    </header>
  );
}

