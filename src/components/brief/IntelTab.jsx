import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Search } from 'lucide-react';
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

function buildCacheKey(physicianId, dateRangeKey) {
  return `intel-${physicianId}-${dateRangeKey}`;
}

function getCachedIntel(physicianId, dateRangeKey) {
  try {
    const raw = sessionStorage.getItem(buildCacheKey(physicianId, dateRangeKey));
    if (!raw) return null;
    const { data, fetchedAt } = JSON.parse(raw);
    if (!data || !fetchedAt) return null;
    if (Date.now() - fetchedAt > INTEL_CACHE_TTL_MS) return null;
    return data;
  } catch {
    return null;
  }
}

function setCachedIntel(physicianId, dateRangeKey, data) {
  try {
    sessionStorage.setItem(
      buildCacheKey(physicianId, dateRangeKey),
      JSON.stringify({ data, fetchedAt: Date.now() })
    );
  } catch {
    // ignore
  }
}

function invalidateCachedIntel(physicianId, dateRangeKey) {
  try {
    sessionStorage.removeItem(buildCacheKey(physicianId, dateRangeKey));
  } catch {
    // ignore
  }
}

function cacheKeyFromRange(start, end) {
  return `${start || 'default'}-${end || 'default'}`;
}

export function IntelTab({ physician, lastContactDate, onUseInPitch }) {
  const [intel, setIntel] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [appliedStartDate, setAppliedStartDate] = useState('');
  const [appliedEndDate, setAppliedEndDate] = useState('');

  const dateRangeKey = cacheKeyFromRange(appliedStartDate, appliedEndDate);
  const selectedWindowText =
    appliedStartDate || appliedEndDate
      ? `${appliedStartDate || '...'} to ${appliedEndDate || 'today'}`
      : null;

  const rangeMessageText =
    appliedStartDate || appliedEndDate
      ? `${appliedStartDate || '...'} to ${appliedEndDate || 'today'}`
      : startDate || endDate
        ? `${startDate || '...'} to ${endDate || 'today'}`
        : null;

  const fetchIntel = useCallback(
    async (forceRefresh, explicitStart, explicitEnd) => {
      if (!physician?.physician_id) return;

      const rangeStart = explicitStart !== undefined ? explicitStart : appliedStartDate;
      const rangeEnd = explicitEnd !== undefined ? explicitEnd : appliedEndDate;
      const key = cacheKeyFromRange(rangeStart, rangeEnd);

      if (!forceRefresh) {
        const cached = getCachedIntel(physician.physician_id, key);
        if (cached) {
          setIntel(cached);
          setHasSearched(true);
          setError(null);
          return;
        }
      }

      setIsLoading(true);
      setError(null);
      try {
        const hasDateRange = Boolean(rangeStart || rangeEnd);
        const data = hasDateRange
          ? await getIntel(physician.physician_id, {
              startDate: rangeStart || undefined,
              endDate: rangeEnd || undefined,
              daysLookback: 90
            })
          : await getIntel(physician.physician_id, 90);
        setIntel(data);
        setHasSearched(true);
        setCachedIntel(physician.physician_id, key, data);
      } catch (err) {
        setError(err.message || 'Failed to load intel');
        setIntel(null);
      } finally {
        setIsLoading(false);
      }
    },
    [physician?.physician_id, appliedStartDate, appliedEndDate]
  );

  useEffect(() => {
    if (!physician?.physician_id) {
      setIntel(null);
      setError(null);
      setHasSearched(false);
      setStartDate('');
      setEndDate('');
      setAppliedStartDate('');
      setAppliedEndDate('');
      return;
    }
    setIntel(null);
    setError(null);
    setHasSearched(false);
    setStartDate('');
    setEndDate('');
    setAppliedStartDate('');
    setAppliedEndDate('');
  }, [physician?.physician_id]);

  const handleRefresh = useCallback(() => {
    if (!physician?.physician_id) return;
    invalidateCachedIntel(physician.physician_id, dateRangeKey);
    fetchIntel(true);
  }, [physician?.physician_id, fetchIntel, dateRangeKey]);

  const handleUseInPitch = (headline) => {
    if (onUseInPitch) {
      onUseInPitch(`How do I work this into my pitch: ${headline}`);
    }
  };

  const handleRunIntelSearch = useCallback(() => {
    setAppliedStartDate(startDate);
    setAppliedEndDate(endDate);
    fetchIntel(false, startDate, endDate);
  }, [startDate, endDate, fetchIntel]);

  const handleApplyDateRange = useCallback(() => {
    setAppliedStartDate(startDate);
    setAppliedEndDate(endDate);
    fetchIntel(false, startDate, endDate);
  }, [startDate, endDate, fetchIntel]);

  const dateRangeControls = (
    <div className="rounded-card border border-bg-border bg-bg-tertiary/50 p-2">
      <div className="mb-1 text-[10px] uppercase tracking-wider text-text-muted">
        Intel Date Range
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[11px] text-text-secondary">
          <span>From</span>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="h-7 rounded border border-bg-border bg-bg-secondary px-2 text-[11px] text-text-primary"
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-text-secondary">
          <span>To</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="h-7 rounded border border-bg-border bg-bg-secondary px-2 text-[11px] text-text-primary"
          />
        </label>
      </div>
    </div>
  );

  if (!physician) return null;

  if (isLoading && !intel) {
    return (
      <div className="space-y-4">
        <p className="text-xs text-text-secondary">
          {rangeMessageText
            ? `Searching for updates from ${rangeMessageText}...`
            : `Searching the last 90 days${lastContactDate ? ` (CRM last touch ${lastContactDate})` : ''}...`}
        </p>
        {dateRangeControls}
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

  if (error && !intel && !isLoading) {
    return (
      <div className="space-y-3">
        {dateRangeControls}
        <div className="rounded-card border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </div>
        <button
          type="button"
          onClick={() => fetchIntel(true, startDate, endDate)}
          className="inline-flex items-center gap-1 rounded border border-accent-primary/60 bg-accent-subtle px-3 py-1.5 text-[11px] font-medium text-accent-primary hover:bg-accent-subtle/80"
        >
          <Search className="h-3 w-3" />
          Try again
        </button>
      </div>
    );
  }

  if (!hasSearched && !isLoading) {
    return (
      <div className="space-y-4">
        <p className="text-xs text-text-secondary">
          Optional date range, then run a web search. Nothing loads until you search.
          {lastContactDate ? (
            <span className="text-text-muted"> CRM last touch: {lastContactDate}.</span>
          ) : null}
        </p>
        {dateRangeControls}
        <button
          type="button"
          onClick={handleRunIntelSearch}
          className="inline-flex items-center gap-1.5 rounded border border-accent-primary/60 bg-accent-subtle px-3 py-2 text-xs font-medium text-accent-primary hover:bg-accent-subtle/80"
        >
          <Search className="h-3.5 w-3.5" />
          Run intel search
        </button>
      </div>
    );
  }

  if (!intel) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="space-y-0.5">
            <p className="text-xs text-text-secondary">
              <span className="font-medium text-text-primary">Web search window: </span>
              {intel.search_window_start && intel.search_window_end
                ? `${intel.search_window_start} – ${intel.search_window_end}`
                : selectedWindowText
                  ? selectedWindowText.replace(' to ', ' – ')
                  : 'Last 90 days (default)'}
            </p>
            <p className="text-[10px] text-text-muted">
              CRM last touch: {intel.last_contact_date || 'unknown'}
              {intel.days_since_contact != null
                ? ` (${intel.days_since_contact} days ago) — not the web search window above`
                : ''}
            </p>
            <p className="text-[10px] text-text-muted/90">
              Date filtering uses web and news search hints plus parsed article dates — not exact for
              every source, especially older or undated pages.
            </p>
          </div>
          <div className="rounded-card border border-bg-border bg-bg-tertiary/50 p-2">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-text-muted">
              Intel Date Range
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1 text-[11px] text-text-secondary">
                <span>From</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="h-7 rounded border border-bg-border bg-bg-secondary px-2 text-[11px] text-text-primary"
                />
              </label>
              <label className="flex flex-col gap-1 text-[11px] text-text-secondary">
                <span>To</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="h-7 rounded border border-bg-border bg-bg-secondary px-2 text-[11px] text-text-primary"
                />
              </label>
              <button
                type="button"
                onClick={handleApplyDateRange}
                className="h-7 rounded border border-accent-primary/60 bg-accent-subtle px-3 text-[11px] font-medium text-accent-primary hover:bg-accent-subtle/80"
              >
                Apply
              </button>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(appliedStartDate || appliedEndDate) && (
            <button
              type="button"
              onClick={() => {
                setStartDate('');
                setEndDate('');
                setAppliedStartDate('');
                setAppliedEndDate('');
                setIntel(null);
                setHasSearched(false);
                setError(null);
              }}
              className="inline-flex items-center rounded border border-bg-border px-2 py-1 text-[11px] text-text-secondary hover:text-text-primary"
            >
              Clear dates
            </button>
          )}
          <button
            type="button"
            onClick={handleRefresh}
            className="inline-flex items-center gap-1 rounded border border-bg-border px-2 py-1 text-[11px] text-text-secondary hover:text-text-primary"
            title="Refresh intel (cache expires after 24h)"
          >
            <RefreshCw className="h-3 w-3" />
            Refresh
          </button>
        </div>
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
          No relevant updates found for the selected date range.
        </p>
      )}
    </div>
  );
}
