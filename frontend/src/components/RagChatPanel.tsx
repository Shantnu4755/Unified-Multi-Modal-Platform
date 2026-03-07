import React, { useEffect, useMemo, useState } from 'react';
import { useMutation } from 'react-query';
import { queryDocuments } from '../services/api.ts';
import { QueryRequest, QueryResponse } from '../types/index.ts';

type ChatMessage =
  | { role: 'user'; content: string }
  | { role: 'assistant'; content: string };

interface RagChatPanelProps {
  documentId?: number;
  canQuery?: boolean;
}

const RagChatPanel: React.FC<RagChatPanelProps> = ({ documentId, canQuery = false }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');

  const storageKey = useMemo(() => {
    const suffix = documentId ? String(documentId) : 'none';
    return `openrag_rag_chat_history_v1_${suffix}`;
  }, [documentId]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) {
        setMessages([]);
        return;
      }
      const parsed = JSON.parse(raw) as Array<{ role: 'user' | 'assistant'; content: string; sources?: unknown }>;
      if (Array.isArray(parsed)) {
        const sanitized = parsed
          .filter((m) => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string')
          .map((m) => ({ role: m.role, content: m.content })) as ChatMessage[];
        setMessages(sanitized);
      }
      else setMessages([]);
    } catch {
      setMessages([]);
    }
  }, [storageKey]);

  useEffect(() => {
    try {
      const sanitized = messages.map((m) => ({ role: m.role, content: m.content }));
      localStorage.setItem(storageKey, JSON.stringify(sanitized));
    } catch {
      // ignore
    }
  }, [messages, storageKey]);

  const canSend = input.trim().length > 0;

  const mutation = useMutation(queryDocuments, {
    onSuccess: (data: QueryResponse) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer },
      ]);
    },
    onError: (err) => {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Request failed: ${(err as Error).message}`,
        },
      ]);
    },
  });

  const handleSend = async () => {
    const question = input.trim();
    if (!question || mutation.isLoading || !documentId || !canQuery) return;

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: question }]);

    const payload: QueryRequest = {
      question,
      document_id: documentId,
      max_results: 5,
      score_threshold: 0.3,
    };

    mutation.mutate(payload);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const emptyState = useMemo(() => {
    if (!documentId) {
      return 'Select a document to view its chat history.';
    }
    if (!canQuery) {
      return 'Document selected. Click Process to enable Q&A.';
    }
    return 'Ask a question about the selected document.';
  }, [canQuery, documentId]);

  return (
    <div className="card flex flex-col h-[70vh]">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">RAG Assistant</h2>
          <p className="text-sm text-gray-600">Chat with your uploaded PDF using retrieval.</p>
        </div>
        <div className="text-xs text-gray-500">
          {documentId ? `Document ID: ${documentId}` : 'No document selected'}
        </div>
      </div>

      <div className="mt-4 flex-1 overflow-auto rounded-lg border border-gray-200 bg-white">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center p-3">
            <div className="text-xs text-gray-600 bg-gray-50 border border-gray-200 rounded-full px-3 py-1">
              {emptyState}
            </div>
          </div>
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
        <label className="block text-xs font-medium text-gray-700 mb-2">Ask a question</label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            !documentId
              ? 'Select a document first'
              : canQuery
                ? 'e.g., Which receipt is uploaded and what is the duration?'
                : 'Process the document to enable Q&A'
          }
          disabled={!documentId || !canQuery || mutation.isLoading}
          className="input min-h-[80px] resize-none"
        />
        <div className="mt-2 flex items-center justify-between">
          <div className="text-xs text-gray-500">
            Enter to send, Shift+Enter for new line
          </div>
          <button
            className="btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={!documentId || !canQuery || !canSend || mutation.isLoading}
            onClick={handleSend}
          >
            {mutation.isLoading ? 'Thinking…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default RagChatPanel;
