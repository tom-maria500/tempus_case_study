import React, { useEffect, useState } from 'react';
import { getProviders } from '../../lib/api';
import { ProviderRow } from './ProviderRow';
import { EmptyState } from '../ui/EmptyState';

const FILTERS = ['All', 'Chicago', 'Houston', 'Boston', 'Tempus Users', 'Non-Users'];

export function ProviderTable({ onSelectProvider, onGenerateBrief, searchQuery = '' }) {
  const [providers, setProviders] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeFilter, setActiveFilter] = useState('All');

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const city =
          activeFilter === 'Chicago' || activeFilter === 'Houston' || activeFilter === 'Boston'
            ? activeFilter
            : null;
        const data = await getProviders(city, 15);
        setProviders(data);
      } catch (err) {
        setError(err.message || 'Failed to load providers');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [activeFilter]);

  const q = (searchQuery || '').trim().toLowerCase();
  const filteredProviders = providers.filter((p) => {
    if (activeFilter === 'Tempus Users' && !p.current_tempus_user) return false;
    if (activeFilter === 'Non-Users' && p.current_tempus_user) return false;
    if (!q) return true;
    const name = (p.name || '').toLowerCase();
    const institution = (p.institution || '').toLowerCase();
    const specialty = (p.specialty || '').toLowerCase();
    const city = (p.city || '').toLowerCase();
    const focus = (p.primary_cancer_focus || '').toLowerCase();
    return (
      name.includes(q) ||
      institution.includes(q) ||
      specialty.includes(q) ||
      city.includes(q) ||
      focus.includes(q)
    );
  });

  return (
    <div className="flex flex-col rounded-card border border-bg-border bg-bg-secondary shadow-tempus">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-bg-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Providers</h2>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((filter) => {
            const isActive = activeFilter === filter;
            return (
              <button
                key={filter}
                type="button"
                onClick={() => setActiveFilter(filter)}
                className={[
                  'rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors duration-150',
                  isActive
                    ? 'border-accent-primary bg-accent-subtle text-accent-primary'
                    : 'border-bg-border bg-bg-tertiary text-text-secondary hover:text-text-primary'
                ].join(' ')}
              >
                {filter}
              </button>
            );
          })}
        </div>
      </div>

      <div className="relative overflow-x-auto">
        {isLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-bg-primary/60 text-xs text-text-secondary">
            Loading providers...
          </div>
        )}

        {error ? (
          <div className="p-6">
            <EmptyState
              title="Unable to load providers"
              description={`${error}. Check that the FastAPI backend is running on http://localhost:8000.`}
            />
          </div>
        ) : filteredProviders.length === 0 && !isLoading ? (
          <div className="p-6">
            <EmptyState
              title="No providers found"
              description="Try adjusting your filters or territory selection."
            />
          </div>
        ) : (
          <table className="min-w-full text-left text-xs">
            <thead className="border-b border-bg-border bg-bg-secondary/80 text-[11px] uppercase tracking-[0.08em] text-text-secondary">
              <tr>
                <th className="px-3 py-2 text-right">Rank</th>
                <th className="px-3 py-2">Physician</th>
                <th className="px-3 py-2">Specialty / Institution</th>
                <th className="px-3 py-2 text-right">Patient Volume</th>
                <th className="px-3 py-2">Priority Score</th>
                <th className="px-3 py-2">Last Contact</th>
                <th className="px-3 py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredProviders.map((p) => (
                <ProviderRow
                  key={p.physician_id}
                  provider={p}
                  onClick={onSelectProvider}
                  onGenerateBrief={onGenerateBrief}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

