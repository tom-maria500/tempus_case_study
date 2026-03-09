import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw } from 'lucide-react';
import { getIntel } from '../../lib/api';
import { IntelCard } from './IntelCard';
import { LoadingPulse } from '../ui/LoadingPulse';

const SECTIONS = [
  { key: 'drug_updates', title: 'Drug & Approval Updates' },
  { key: 'publications', title: 'Their Publications' },
  { key: 'tempus_updates', title: 'Tempus Updates' },
  { key: 'competitive_intel', title: 'Competitive Intel' }
];

const INTEL_CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

function getCachedIntel(physicianId) {
  try {
    const raw = sessionStorage.getItem(`intel-${physicianId}`);
    if (!raw) return null;
    const { data, fetchedAt } = JSON.parse(raw);
    if (!data || !fetchedAt) return null;
    if (Date.now() - fetchedAt > INTEL_CACHE_TTL_MS) return null;
    return data;
  } catch {
    return null;
  }
}

function setCachedIntel(physicianId, data) {
  try {
    sessionStorage.setItem(
      `intel-${physicianId}`,
      JSON.stringify({ data, fetchedAt: Date.now() })
    );
  } catch {
    // ignore
  }
}

function invalidateCachedIntel(physicianId) {
  try {
    sessionStorage.removeItem(`intel-${physicianId}`);
  } catch {
    // ignore
  }
}

export function IntelTab({ physician, lastContactDate, onUseInPitch }) {
  const [intel, setIntel] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetch = useCallback(
    async (forceRefresh = false) => {
      if (!physician?.physician_id) return;

      if (!forceRefresh) {
        const cached = getCachedIntel(physician.physician_id);
        if (cached) {
          setIntel(cached);
          return;
        }
      }

      setIsLoading(true);
      setError(null);
      try {
        const data = await getIntel(physician.physician_id, 90);
        setIntel(data);
        setCachedIntel(physician.physician_id, data);
      } catch (err) {
        setError(err.message || 'Failed to load intel');
        setIntel(null);
      } finally {
        setIsLoading(false);
      }
    },
    [physician?.physician_id]
  );

  useEffect(() => {
    if (!physician?.physician_id) {
      setIntel(null);
      setError(null);
      return;
    }
    const cached = getCachedIntel(physician.physician_id);
    if (cached) {
      setIntel(cached);
      setError(null);
      return;
    }
    setIntel(null);
    fetch(true);
  }, [physician?.physician_id, fetch]);

  const handleRefresh = useCallback(() => {
    if (!physician?.physician_id) return;
    invalidateCachedIntel(physician.physician_id);
    fetch(true);
  }, [physician?.physician_id, fetch]);

  const handleUseInPitch = (headline) => {
    if (onUseInPitch) {
      onUseInPitch(`How do I work this into my pitch: ${headline}`);
    }
  };

  if (!physician) return null;

  if (isLoading && !intel) {
    return (
      <div className="space-y-4">
        <p className="text-xs text-text-secondary">
          Searching for updates since {lastContactDate || 'last contact'}...
        </p>
        <LoadingPulse />
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-24 animate-pulse rounded-card border border-bg-border bg-bg-tertiary"
            />
          ))}
        </div>
      </div>
    );
  }

  if (error && !intel) {
    return (
      <div className="space-y-2">
        <div className="rounded-card border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </div>
        <button
          type="button"
          onClick={() => fetch(true)}
          className="text-xs text-accent-primary hover:underline"
        >
          Try again
        </button>
      </div>
    );
  }

  if (!intel) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-secondary">
          Updates since {intel.last_contact_date || 'unknown'} (
          {intel.days_since_contact} days ago)
        </p>
        <button
          type="button"
          onClick={handleRefresh}
          className="inline-flex items-center gap-1 text-[11px] text-text-secondary hover:text-text-primary"
          title="Refresh intel (cache expires after 24h)"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </button>
      </div>
      {SECTIONS.map(({ key, title }) => {
        const items = intel[key] || [];
        if (items.length === 0) return null;
        return (
          <div key={key}>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">
              {title}
            </h4>
            <div className="space-y-2">
              {items.map((item, i) => (
                <IntelCard
                  key={i}
                  item={item}
                  onUseInPitch={handleUseInPitch}
                />
              ))}
            </div>
          </div>
        );
      })}
      {SECTIONS.every((s) => !(intel[s.key]?.length)) && (
        <p className="text-xs text-text-muted">
          No relevant updates found in the last 90 days.
        </p>
      )}
    </div>
  );
}
