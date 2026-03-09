import React, { useState } from 'react';
import { X } from 'lucide-react';
import { logOutcome } from '../../lib/api';

const OUTCOMES = [
  { value: 'committed_to_pilot', label: 'Committed to pilot' },
  { value: 'positive_followup', label: 'Positive — follow-up scheduled' },
  { value: 'neutral_evaluating', label: 'Neutral — still evaluating' },
  { value: 'negative_not_interested', label: 'Negative — not interested' },
  { value: 'no_show', label: 'No show / rescheduled' }
];

const CONCERNS = [
  { value: 'turnaround_time', label: 'Turnaround time' },
  { value: 'cost_reimbursement', label: 'Cost / reimbursement' },
  { value: 'competitor_loyalty', label: 'Competitor loyalty' },
  { value: 'emr_integration', label: 'EMR integration' },
  { value: 'staff_bandwidth', label: 'Staff bandwidth' },
  { value: 'ai_skepticism', label: 'AI skepticism' },
  { value: 'no_concern', label: 'No concern raised' },
  { value: 'other', label: 'Other' }
];

export function OutcomeLoggerModal({ open, onClose, physician, onLogged }) {
  const [outcome, setOutcome] = useState('');
  const [mainConcern, setMainConcern] = useState('');
  const [concernDetail, setConcernDetail] = useState('');
  const [nextStep, setNextStep] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const reset = () => {
    setOutcome('');
    setMainConcern('');
    setConcernDetail('');
    setNextStep('');
    setResult(null);
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!physician?.physician_id) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const res = await logOutcome({
        physician_id: physician.physician_id,
        outcome,
        main_concern: mainConcern === 'other' ? (concernDetail || 'other') : mainConcern,
        concern_detail: mainConcern === 'other' ? concernDetail : undefined,
        next_step: nextStep,
        meeting_date: new Date().toISOString().split('T')[0]
      });
      setResult(res);
      onLogged?.(res);
    } catch (err) {
      setError(err.message || 'Failed to log outcome');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenChat = () => {
    if (result?.suggested_next_action && onLogged) {
      onLogged({ ...result, openChatWith: result.suggested_next_action });
    }
    handleClose();
  };

  if (!open) return null;

  const meetingDate = new Date().toISOString().split('T')[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className="w-full max-w-[480px] rounded-card border border-bg-border bg-bg-secondary shadow-tempus"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between border-b border-bg-border px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-text-primary">
              Log Meeting — {physician?.name ?? 'Physician'}
            </h2>
            <p className="mt-0.5 text-xs text-text-secondary">
              {physician?.institution} · {meetingDate}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-full p-1 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {result ? (
          <div className="space-y-4 px-5 py-4">
            <div className="rounded-card border border-success/40 bg-success/10 px-3 py-2 text-xs text-success">
              ✓ Meeting logged
            </div>
            <p className="text-sm text-text-primary">
              Priority score updated: {result.new_priority_score}
              {result.score_delta !== 0 && (
                <span className={result.score_delta > 0 ? 'text-success' : 'text-danger'}>
                  {' '}({result.score_delta > 0 ? '+' : ''}{result.score_delta})
                </span>
              )}
            </p>
            <div>
              <p className="mb-1 text-xs font-semibold text-text-secondary">
                Suggested next action
              </p>
              <p className="text-sm text-text-primary">
                {result.suggested_next_action}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleClose}
                className="flex-1 rounded-input border border-bg-border px-3 py-2 text-sm text-text-primary hover:bg-bg-tertiary"
              >
                Close
              </button>
              <button
                type="button"
                onClick={handleOpenChat}
                className="flex-1 rounded-input bg-black px-3 py-2 text-sm text-white hover:opacity-90"
              >
                Open Chat to Prep →
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 px-5 py-4">
            <div>
              <p className="mb-2 text-sm font-semibold text-text-primary">
                How did it go?
              </p>
              <div className="space-y-1">
                {OUTCOMES.map((o) => (
                  <label
                    key={o.value}
                    className="flex cursor-pointer items-center gap-2 rounded-input border px-3 py-2 transition-colors"
                    style={{
                      borderColor: outcome === o.value ? '#000' : '#1E2D40',
                      backgroundColor: outcome === o.value ? '#000' : 'transparent',
                      color: outcome === o.value ? '#fff' : '#666'
                    }}
                  >
                    <input
                      type="radio"
                      name="outcome"
                      value={o.value}
                      checked={outcome === o.value}
                      onChange={() => setOutcome(o.value)}
                      className="sr-only"
                    />
                    {o.label}
                  </label>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-semibold text-text-primary">
                What was their main concern?
              </p>
              <div className="space-y-1">
                {CONCERNS.map((c) => (
                  <label
                    key={c.value}
                    className="flex cursor-pointer items-center gap-2 rounded-input border px-3 py-2 transition-colors"
                    style={{
                      borderColor: mainConcern === c.value ? '#000' : '#1E2D40',
                      backgroundColor: mainConcern === c.value ? '#000' : 'transparent',
                      color: mainConcern === c.value ? '#fff' : '#666'
                    }}
                  >
                    <input
                      type="radio"
                      name="concern"
                      value={c.value}
                      checked={mainConcern === c.value}
                      onChange={() => setMainConcern(c.value)}
                      className="sr-only"
                    />
                    {c.label}
                  </label>
                ))}
                {mainConcern === 'other' && (
                  <input
                    type="text"
                    value={concernDetail}
                    onChange={(e) => setConcernDetail(e.target.value)}
                    placeholder="Describe the concern"
                    className="w-full rounded-input border border-bg-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
                  />
                )}
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-semibold text-text-primary">
                What&apos;s the next step?
              </p>
              <input
                type="text"
                value={nextStep}
                onChange={(e) => setNextStep(e.target.value)}
                placeholder="e.g. Send de-identified NSCLC report and schedule Epic demo"
                className="w-full rounded-input border border-bg-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
              />
            </div>

            {error && (
              <p className="text-xs text-danger">{error}</p>
            )}

            <button
              type="submit"
              disabled={!outcome || !nextStep.trim() || isSubmitting}
              className="w-full rounded-input bg-black px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {isSubmitting ? 'Logging...' : 'Log & Update Profile'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
