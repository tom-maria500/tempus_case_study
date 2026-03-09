import React, { useState, useEffect, useRef, useCallback } from 'react';
import { sendChat } from '../../lib/api';
import { ChatInput } from './ChatInput';
import { ChatMessage, TypingIndicator } from './ChatMessage';

const STARTER_CHIPS = [
  'How do I handle her main objection?',
  'Make the meeting script punchier',
  'What else might come up?'
];

export function ChatPanel({ physician, brief, preloadMessage, onPreloadSent }) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef(null);

  const physicianName = physician?.name ?? 'this physician';
  const displayName = physicianName.trimStart().toLowerCase().startsWith('dr.')
    ? physicianName
    : `Dr. ${physicianName}`;

  useEffect(() => {
    if (!brief || !physician) return;
    const greeting = `I've reviewed ${displayName}'s brief. Ask me anything to sharpen your pitch or prep for objections.`;
    setMessages([
      { role: 'assistant', content: greeting, followups: STARTER_CHIPS }
    ]);
  }, [brief?.meeting_script, physician?.physician_id, displayName]);

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, scrollToBottom]);

  useEffect(() => {
    if (!preloadMessage?.trim() || isLoading) return;
    const msg = preloadMessage.trim();
    onPreloadSent?.();
    sendMessage(msg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preloadMessage]);

  const buildBriefContext = () => {
    if (!brief) return {};
    const objection =
      typeof brief.objection_handler === 'string'
        ? brief.objection_handler
        : brief.objection_handler?.response ?? JSON.stringify(brief.objection_handler ?? '');
    return {
      meeting_script: brief.meeting_script ?? '',
      objection_handler: objection,
      retrieved_kb_chunks: brief.retrieved_kb_chunks ?? []
    };
  };

  const sendMessage = useCallback(
    async (text) => {
      if (!physician?.physician_id || !brief || !text.trim() || isLoading) return;

      const userMessage = { role: 'user', content: text.trim() };
      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);

      const payload = {
        physician_id: physician.physician_id,
        message: text.trim(),
        conversation_history: messages.map((m) => ({ role: m.role, content: m.content })),
        brief_context: buildBriefContext()
      };

      try {
        const res = await sendChat(payload);
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: res.response,
            followups: res.suggested_followups ?? []
          }
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Error: ${err.message}`, followups: [] }
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [physician?.physician_id, physician?.name, brief, messages, isLoading]
  );

  if (!brief || !physician) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="max-h-64 space-y-3 overflow-y-auto rounded-card border border-bg-border bg-bg-secondary/60 p-3">
        {messages.map((m, i) => (
          <ChatMessage
            key={i}
            role={m.role}
            content={m.content}
            followups={m.followups}
            isLatest={!isLoading && i === messages.length - 1}
            onFollowupClick={sendMessage}
          />
        ))}
        {isLoading && <TypingIndicator />}
        <div ref={scrollRef} />
      </div>
      <ChatInput onSend={sendMessage} disabled={isLoading} />
    </div>
  );
}
