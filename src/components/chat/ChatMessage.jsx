import React from 'react';
import { FollowUpChips } from './FollowUpChips';

export function ChatMessage({ role, content, followups, isLatest, onFollowupClick }) {
  const isUser = role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={[
          'max-w-[85%] rounded-card px-3 py-2 text-sm',
          isUser
            ? 'bg-accent-primary text-bg-primary'
            : 'bg-bg-tertiary text-text-primary'
        ].join(' ')}
      >
        <p className="whitespace-pre-wrap leading-relaxed">{content}</p>
        {followups && followups.length > 0 && (
          <FollowUpChips
            chips={followups}
            clickable={isLatest}
            onSelect={onFollowupClick}
          />
        )}
      </div>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex gap-1 rounded-card bg-bg-tertiary px-3 py-2">
        <span className="h-2 w-2 animate-pulse rounded-full bg-accent-primary" />
        <span
          className="h-2 w-2 animate-pulse rounded-full bg-accent-primary"
          style={{ animationDelay: '150ms' }}
        />
        <span
          className="h-2 w-2 animate-pulse rounded-full bg-accent-primary"
          style={{ animationDelay: '300ms' }}
        />
      </div>
    </div>
  );
}
