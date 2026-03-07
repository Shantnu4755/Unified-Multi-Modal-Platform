import React, { useEffect, useMemo, useState } from 'react';
import { useMutation } from 'react-query';
import { generalChat } from '../services/api.ts';

type ChatMessage =
  | { role: 'user'; content: string }
  | { role: 'assistant'; content: string };

interface GeneralChatPanelProps {
  heightClass?: string;
  compact?: boolean;
}

const GeneralChatPanel: React.FC<GeneralChatPanelProps> = ({
  heightClass = 'h-[70vh]',
  compact = false,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');

  const storageKey = useMemo(() => 'openrag_general_chat_history_v1', []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as ChatMessage[];
      if (Array.isArray(parsed)) setMessages(parsed);
    } catch {
      // ignore
    }
  }, [storageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // ignore
    }
  }, [messages, storageKey]);

  const mutation = useMutation<{ message: string; reply: string }, Error, { message: string }>(generalChat, {
    onSuccess: (data) => {
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);
    },
    onError: (err) => {
      setMessages((prev) => [...prev, { role: 'assistant', content: `Request failed: ${err.message}` }]);
    },
  });

  const handleSend = () => {
    const message = input.trim();
    if (!message || mutation.isLoading) return;

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    mutation.mutate({ message });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={`card flex flex-col ${heightClass}`}>
      <div>
        <h2 className={compact ? 'text-sm font-semibold text-gray-900' : 'text-lg font-semibold text-gray-900'}>
          General Chat
        </h2>
        {!compact && <p className="text-sm text-gray-600">Chat with the model without using RAG.</p>}
      </div>

      <div className="mt-4 flex-1 overflow-auto rounded-lg border border-gray-200 bg-white">
        {messages.length === 0 ? (
          <div className="p-6 text-sm text-gray-600">Ask anything. This mode doesn’t use your documents.</div>
        ) : (
          <div className="p-4 space-y-4">
            {messages.map((m, idx) => (
              <div key={idx} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <div
                  className={
                    m.role === 'user'
                      ? 'max-w-[85%] rounded-2xl bg-primary-600 text-white px-4 py-2 text-sm whitespace-pre-wrap'
                      : 'max-w-[85%] rounded-2xl bg-gray-100 text-gray-900 px-4 py-2 text-sm whitespace-pre-wrap'
                  }
                >
                  {m.content}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-4">
        <label className="block text-xs font-medium text-gray-700 mb-2">Message</label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g., Explain RAG in simple terms"
          disabled={mutation.isLoading}
          className={compact ? 'input min-h-[56px] resize-none' : 'input min-h-[80px] resize-none'}
        />
        <div className="mt-2 flex items-center justify-between">
          <div className="text-xs text-gray-500">Enter to send, Shift+Enter for new line</div>
          <button
            className="btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={!input.trim() || mutation.isLoading}
            onClick={handleSend}
          >
            {mutation.isLoading ? 'Thinking…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default GeneralChatPanel;
