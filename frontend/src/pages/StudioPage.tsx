import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from 'react-query';
import DocumentUpload from '../components/DocumentUpload.tsx';
import RagChatPanel from '../components/RagChatPanel.tsx';
import GeneralChatPanel from '../components/GeneralChatPanel.tsx';
import { getDocuments, processDocument } from '../services/api.ts';
import { Document } from '../types/index.ts';

type ToolKey = 'rag' | 'chat' | 'image' | 'voice';

const StudioPage: React.FC = () => {
  const [activeTool, setActiveTool] = useState<ToolKey>('rag');
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | undefined>(undefined);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: documents } = useQuery<Document[]>('documents', getDocuments, {
    enabled: activeTool === 'rag',
    refetchInterval: activeTool === 'rag' ? 5000 : false,
  });

  const processMutation = useMutation(processDocument, {
    onSuccess: () => queryClient.invalidateQueries('documents'),
  });

  const selectedDocument = useMemo(() => {
    if (!documents || !selectedDocumentId) return undefined;
    return documents.find((d) => d.id === selectedDocumentId);
  }, [documents, selectedDocumentId]);

  const canUseRag = selectedDocument?.status === 'completed';

  const ToolButton: React.FC<{ k: ToolKey; label: string; desc: string }> = ({ k, label, desc }) => (
    <button
      onClick={() => setActiveTool(k)}
      className={
        activeTool === k
          ? 'w-full text-left rounded-xl border border-primary-200 bg-primary-50 p-4'
          : 'w-full text-left rounded-xl border border-gray-200 bg-white p-4 hover:bg-gray-50'
      }
    >
      <div className="font-semibold text-gray-900">{label}</div>
      <div className="text-xs text-gray-600 mt-1">{desc}</div>
    </button>
  );

  return (
    <div className="max-w-7xl mx-auto">
      <div className="rounded-2xl bg-gradient-to-r from-slate-900 via-blue-900 to-slate-900 px-6 py-8 text-white">
        <div className="text-2xl font-bold">AI Studio - Unified Multi-Modal Platform</div>
        <div className="mt-1 text-sm text-blue-100">Text | Image | Audio | Video | Agents</div>
      </div>

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-4 space-y-6">
          {activeTool === 'rag' && (
            <div className="card">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-lg font-semibold text-gray-900">Documents</div>
                  <div className="text-sm text-gray-600">Upload a PDF, then select and process it for RAG.</div>
                </div>
              </div>

              <div className="mt-4">
                <DocumentUpload />
              </div>

              <div className="mt-4">
                <label className="block text-xs font-medium text-gray-700 mb-2">Select Document</label>
                <select
                  className="input"
                  value={selectedDocumentId ?? ''}
                  onChange={(e) => setSelectedDocumentId(e.target.value ? Number(e.target.value) : undefined)}
                >
                  <option value="">-- choose --</option>
                  {(documents || []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.original_filename} ({d.status})
                    </option>
                  ))}
                </select>

                {selectedDocument && selectedDocument.status !== 'completed' && (
                  <div className="mt-3 flex items-center justify-between">
                    <div className="text-xs text-gray-600">
                      Status: <span className="font-medium">{selectedDocument.status}</span>
                    </div>
                    <button
                      className="btn-primary text-sm"
                      disabled={processMutation.isLoading || selectedDocument.status === 'processing'}
                      onClick={() => processMutation.mutate(selectedDocument.id)}
                    >
                      {processMutation.isLoading ? 'Processing…' : 'Process'}
                    </button>
                  </div>
                )}

                {selectedDocument && canUseRag && (
                  <div className="mt-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg p-2">
                    Ready: document is processed and searchable.
                  </div>
                )}

                {selectedDocument && !canUseRag && selectedDocument.status === 'failed' && (
                  <div className="mt-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg p-2">
                    Processing failed. Click Process to retry.
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="card">
            <div className="text-lg font-semibold text-gray-900">AI Tools</div>
            <div className="text-sm text-gray-600 mt-1">Choose what you want to do.</div>
            <div className="mt-4 space-y-3">
              <ToolButton k="rag" label="RAG Assistant" desc="Chat & summarize uploaded PDFs." />
              <ToolButton k="image" label="Image" desc="Generation / classification (coming soon)." />
              <ToolButton k="voice" label="Voice" desc="Speech-to-text / text-to-speech (coming soon)." />
            </div>
          </div>
        </div>

        <div className="lg:col-span-8 space-y-6">
          {activeTool === 'rag' && <RagChatPanel documentId={selectedDocumentId} canQuery={canUseRag} />}

          {activeTool === 'image' && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-900">Image</h2>
              <p className="text-sm text-gray-600 mt-1">
                Add HuggingFace/Replicate providers for image generation, classification, and image search.
              </p>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border rounded-xl p-4">
                  <div className="font-medium text-gray-900">Image Generation</div>
                  <div className="text-xs text-gray-600 mt-1">Prompt to generated images to saved assets.</div>
                </div>
                <div className="border rounded-xl p-4">
                  <div className="font-medium text-gray-900">Image Classification</div>
                  <div className="text-xs text-gray-600 mt-1">Upload image to labels to stored metadata.</div>
                </div>
              </div>
            </div>
          )}

          {activeTool === 'voice' && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-900">Voice</h2>
              <p className="text-sm text-gray-600 mt-1">
                Add Whisper STT + TTS so you can speak to the assistant and generate audio outputs.
              </p>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border rounded-xl p-4">
                  <div className="font-medium text-gray-900">Speech to Text</div>
                  <div className="text-xs text-gray-600 mt-1">Upload audio to transcript to summary.</div>
                </div>
                <div className="border rounded-xl p-4">
                  <div className="font-medium text-gray-900">Text to Speech</div>
                  <div className="text-xs text-gray-600 mt-1">Generate voice from summaries or answers.</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="fixed bottom-6 right-6 z-50">
        {isChatOpen && (
          <div className="mb-3 w-[360px] max-w-[calc(100vw-3rem)]">
            <GeneralChatPanel heightClass="h-[520px]" />
          </div>
        )}

        <button
          type="button"
          className="btn-primary rounded-full w-12 h-12 flex items-center justify-center"
          onClick={() => setIsChatOpen((v) => !v)}
          aria-label={isChatOpen ? 'Close chat' : 'Open chat'}
        >
          {isChatOpen ? '×' : '💬'}
        </button>
      </div>
    </div>
  );
};

export default StudioPage;
