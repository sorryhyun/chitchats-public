import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { API_BASE_URL, getFetchOptions } from '../../services/apiClient';

interface ConversationFile {
  id: string;
  filename: string;
  project: string;
  modified: string;
  size: number;
}

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ExportModal = ({ isOpen, onClose }: ExportModalProps) => {
  const { t } = useTranslation('sidebar');
  const modalRef = useFocusTrap<HTMLDivElement>(isOpen);
  const [conversations, setConversations] = useState<ConversationFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);

  // Handle Escape key to close modal
  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      fetchConversations();
    }
  }, [isOpen]);

  const fetchConversations = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/exports/conversations`,
        getFetchOptions()
      );
      if (!response.ok) {
        throw new Error('Failed to fetch conversations');
      }
      const data = await response.json();
      setConversations(data.conversations);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = (conv: ConversationFile, simplified: boolean) => {
    const url = `${API_BASE_URL}/exports/conversations/${encodeURIComponent(conv.project)}/${encodeURIComponent(conv.id)}?simplified=${simplified}`;

    // Create a temporary anchor to trigger download
    const a = document.createElement('a');
    a.href = url;
    a.download = simplified ? `${conv.id}_simplified.jsonl` : conv.filename;

    // Add auth header via fetch and create blob URL
    fetch(url, getFetchOptions())
      .then(res => res.blob())
      .then(blob => {
        const blobUrl = URL.createObjectURL(blob);
        a.href = blobUrl;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      })
      .catch(err => {
        console.error('Download failed:', err);
      });
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(parseFloat(timestamp) * 1000);
    return date.toLocaleString();
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Get unique projects
  const projects = [...new Set(conversations.map(c => c.project))];

  // Filter conversations by selected project
  const filteredConversations = selectedProject
    ? conversations.filter(c => c.project === selectedProject)
    : conversations;

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={modalRef}
        className="modal-container max-w-3xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 sm:w-6 sm:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              </div>
              <div className="min-w-0">
                <h2 className="text-lg sm:text-2xl font-bold text-white truncate">{t('exportConversations')}</h2>
                <p className="text-slate-200 text-xs sm:text-sm">Claude Code JSONL</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-white hover:bg-white/20 active:bg-white/30 p-2 rounded-lg transition-colors flex-shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation"
            >
              <svg className="w-5 h-5 sm:w-6 sm:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Project Filter */}
        {projects.length > 1 && (
          <div className="px-6 py-3 border-b border-slate-200 bg-slate-50">
            <select
              value={selectedProject || ''}
              onChange={e => setSelectedProject(e.target.value || null)}
              className="w-full px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            >
              <option value="">{t('allProjects')}</option>
              {projects.map(project => (
                <option key={project} value={project}>{project}</option>
              ))}
            </select>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-700"></div>
            </div>
          ) : error ? (
            <div className="text-center py-12 text-red-600">
              <p>{error}</p>
              <button
                onClick={fetchConversations}
                className="mt-4 px-4 py-2 bg-slate-100 hover:bg-slate-200 rounded-lg text-sm"
              >
                {t('retry')}
              </button>
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <svg className="w-16 h-16 mx-auto mb-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p>{t('noConversationsFound')}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredConversations.map(conv => (
                <div
                  key={`${conv.project}-${conv.id}`}
                  className="bg-slate-50 rounded-lg p-4 hover:bg-slate-100 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="font-mono text-sm text-slate-800 truncate" title={conv.id}>
                        {conv.id}
                      </p>
                      <p className="text-xs text-slate-500 mt-1">
                        {conv.project} &middot; {formatDate(conv.modified)} &middot; {formatSize(conv.size)}
                      </p>
                    </div>
                    <div className="flex gap-2 flex-shrink-0">
                      <button
                        onClick={() => handleDownload(conv, false)}
                        className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded text-xs font-medium transition-colors"
                        title={t('downloadRaw')}
                      >
                        {t('raw')}
                      </button>
                      <button
                        onClick={() => handleDownload(conv, true)}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-medium transition-colors"
                        title={t('downloadSimplified')}
                      >
                        {t('simplified')}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="modal-footer flex items-center justify-between gap-4">
          <p className="text-xs text-slate-500 flex-1">
            {t('exportDescription')}
          </p>
          <button
            onClick={onClose}
            className="btn-primary px-4 sm:px-6 py-2.5 sm:py-3 text-sm sm:text-base min-h-[44px] touch-manipulation flex-shrink-0"
          >
            {t('close', 'Close')}
          </button>
        </div>
      </div>
    </div>
  );
};
