import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';

const LINE_HEIGHT = 24;
const MAX_LINES = 4;

export function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState('');
  const textareaRef = useRef(null);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_LINES * LINE_HEIGHT)}px`;
  }, [value]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
  }, [value, disabled, onSend]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex gap-2 rounded-input border border-bg-border bg-bg-tertiary p-2">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask a follow-up — refine the pitch, prep for objections..."
        disabled={disabled}
        rows={1}
        className="min-h-[2rem] max-h-24 flex-1 resize-none border-none bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-0 disabled:opacity-50"
      />
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!value.trim() || disabled}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-primary text-bg-primary transition-colors hover:bg-accent-hover disabled:opacity-40 disabled:hover:bg-accent-primary"
      >
        <Send className="h-4 w-4" />
      </button>
    </div>
  );
}
