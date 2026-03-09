import React from 'react';

export function SearchBar({ icon: Icon, placeholder, onChange }) {
  return (
    <div className="flex items-center gap-2 rounded-input border border-bg-border bg-bg-secondary px-3 py-1.5 text-sm text-text-secondary shadow-tempus focus-within:border-accent-primary focus-within:ring-1 focus-within:ring-accent-primary transition-colors duration-150">
      {Icon && <Icon className="h-4 w-4 text-text-muted" />}
      <input
        type="text"
        placeholder={placeholder}
        onChange={(e) => onChange?.(e.target.value)}
        className="flex-1 border-none bg-transparent text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-0"
      />
    </div>
  );
}

