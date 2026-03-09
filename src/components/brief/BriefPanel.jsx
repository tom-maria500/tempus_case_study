import React, { useState, useCallback } from 'react';
import { X, ClipboardList, RefreshCw } from 'lucide-react';
import { MeetingScript } from './MeetingScript';
import { ObjectionHandler } from './ObjectionHandler';
import { ContextCard } from './ContextCard';
import { ChatPanel } from '../chat/ChatPanel';
import { IntelTab } from './IntelTab';
import { OutcomeLoggerModal } from './OutcomeLoggerModal';
import { LoadingPulse } from '../ui/LoadingPulse';
import { StatusBadge } from '../ui/StatusBadge';
import { PriorityBadge } from '../providers/PriorityBadge';

export function BriefPanel({
  open,
  onClose,
  physician,
  brief,
  isLoading,
  error,
  onProviderUpdate,
  onRefetchBrief
}) {
  const [activeTab, setActiveTab] = useState('brief');
  const [outcomeModalOpen, setOutcomeModalOpen] = useState(false);
  const [preloadMessage, setPreloadMessage] = useState(null);

  const handleUseInPitch = useCallback((text) => {
    setPreloadMessage(text);
  }, []);

  const handlePreloadSent = useCallback(() => {
    setPreloadMessage(null);
  }, []);

  const handleOutcomeLogged = useCallback(
    (result) => {
      if (result?.openChatWith) {
        setPreloadMessage(result.openChatWith);
        setActiveTab('brief');
      }
      onProviderUpdate?.(result, physician);
    },
    [onProviderUpdate, physician]
  );

  if (!open) return null;

  const isTempusUser = physician?.current_tempus_user;
  const lastContactDate =
    physician?.last_contact_date || brief?.physician?.last_contact_date;

  return (
    <>
      <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-xl border-l border-bg-border bg-bg-secondary shadow-tempus">
        <div className="flex h-full flex-col">
          <header className="flex items-start justify-between border-b border-bg-border px-5 py-4">
            <div>
              <h2 className="text-base font-semibold text-text-primary">
                {physician?.name ?? 'Selected Physician'}
              </h2>
              <p className="mt-0.5 text-xs text-text-secondary">
                {physician?.institution} · {physician?.specialty}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <StatusBadge type={isTempusUser ? 'tempus_user' : 'prospect'} />
                {physician?.specialty && (
                  <span className="rounded-badge border border-accent-primary/60 px-2 py-0.5 text-[11px] text-accent-primary">
                    {physician.specialty}
                  </span>
                )}
                {physician?.priority_score != null && (
                  <div className="ml-2 flex items-center gap-1 text-xs text-text-secondary">
                    <span className="text-[10px] uppercase tracking-[0.16em] text-text-muted">
                      Priority Score
                    </span>
                    <PriorityBadge score={physician.priority_score} />
                  </div>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full p-1 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          {brief && (
            <div className="flex items-center border-b border-bg-border">
              <button
                type="button"
                onClick={() => setActiveTab('brief')}
                className={`flex-1 px-4 py-2 text-sm font-medium ${
                  activeTab === 'brief'
                    ? 'border-b-2 border-accent-primary text-accent-primary'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                Brief
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('intel')}
                className={`flex-1 px-4 py-2 text-sm font-medium ${
                  activeTab === 'intel'
                    ? 'border-b-2 border-accent-primary text-accent-primary'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                Pre-Call Intel
              </button>
              {onRefetchBrief && physician && (
                <button
                  type="button"
                  onClick={() => onRefetchBrief(physician)}
                  disabled={isLoading}
                  className="px-3 py-2 text-[11px] text-text-secondary hover:text-text-primary disabled:opacity-50"
                  title="Regenerate brief"
                >
                  <RefreshCw className="h-4 w-4" />
                </button>
              )}
            </div>
          )}

          {brief && physician && (
            <div className="border-b border-bg-border px-5 py-2">
              <button
                type="button"
                onClick={() => setOutcomeModalOpen(true)}
                className="inline-flex items-center gap-2 rounded-input border border-bg-border px-3 py-1.5 text-sm text-text-primary transition-colors hover:bg-bg-tertiary"
              >
                <ClipboardList className="h-4 w-4" />
                Log Meeting Outcome
              </button>
            </div>
          )}

          {isLoading && (
            <div className="border-b border-bg-border bg-accent-subtle/30 px-5 py-2 text-xs text-text-secondary">
              Generating brief...
            </div>
          )}

          <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
            {isLoading ? (
              <LoadingPulse />
            ) : error ? (
              <div className="rounded-card border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
                {error === 'Physician not found'
                  ? 'Physician not found. Try selecting a different provider from the table.'
                  : error === 'Service unavailable'
                  ? 'Service unavailable — please retry in a moment.'
                  : error}
              </div>
            ) : brief && activeTab === 'brief' ? (
              <>
                <MeetingScript text={brief.meeting_script} />
                <ObjectionHandler
                  objection={brief.objection_handler?.objection}
                  response={
                    brief.objection_handler?.response ??
                    brief.objection_handler
                  }
                />
                <ContextCard
                  physician={physician}
                  priorityRationale={brief.priority_rationale}
                />
                <div className="flex flex-col gap-4 border-t border-bg-border pt-4">
                  <div>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">
                      Follow-up Chat
                    </h3>
                    <ChatPanel
                      physician={physician}
                      brief={brief}
                      preloadMessage={preloadMessage}
                      onPreloadSent={handlePreloadSent}
                    />
                  </div>
                </div>
              </>
            ) : brief && activeTab === 'intel' ? (
              <IntelTab
                physician={physician}
                lastContactDate={lastContactDate}
                onUseInPitch={handleUseInPitch}
              />
            ) : brief ? null : (
              <div className="rounded-card border border-bg-border bg-bg-secondary/60 px-4 py-8 text-center text-xs text-text-secondary">
                Select a provider and choose &quot;Generate Brief&quot; to see a
                tailored script, objection handler, and rationale.
              </div>
            )}
          </div>
        </div>
      </aside>

      <OutcomeLoggerModal
        open={outcomeModalOpen}
        onClose={() => setOutcomeModalOpen(false)}
        physician={physician}
        onLogged={handleOutcomeLogged}
      />
    </>
  );
}
