import { useState, useEffect } from 'react';
import { useFocusTrap } from '../hooks/useFocusTrap';
import type { Agent, AgentUpdate } from '../types';
import { agentService, getAgentProfilePicUrl } from '../services/agentService';
import { useAuth } from '../contexts/AuthContext';

interface AgentProfileModalProps {
  agent: Agent;
  onClose: () => void;
  onUpdate: () => void;
  onDelete?: (agentId: number) => Promise<void>;
}

export const AgentProfileModal = ({ agent, onClose, onUpdate, onDelete }: AgentProfileModalProps) => {
  const { isAdmin } = useAuth();
  const [editedAgent, setEditedAgent] = useState<Agent>(agent);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Focus trap for modal
  const modalRef = useFocusTrap<HTMLDivElement>(true);

  // Handle Escape key to close modal
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const handleProfilePicChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      // Validate file type
      if (!file.type.startsWith('image/')) {
        setError('Please select an image file');
        return;
      }

      // Validate file size (max 5MB)
      if (file.size > 5 * 1024 * 1024) {
        setError('Image size must be less than 5MB');
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        const base64 = reader.result as string;
        setEditedAgent({ ...editedAgent, profile_pic: base64 });
        setError(null);
      };
      reader.onerror = () => {
        setError('Failed to read image file');
      };
      reader.readAsDataURL(file);
    }
  };

  const handleRemoveProfilePic = () => {
    setEditedAgent({ ...editedAgent, profile_pic: null });
  };

  const handleSave = async () => {
    try {
      setIsSaving(true);
      setError(null);

      const updateData: AgentUpdate = {
        profile_pic: editedAgent.profile_pic,
        in_a_nutshell: editedAgent.in_a_nutshell,
        characteristics: editedAgent.characteristics,
        backgrounds: editedAgent.backgrounds,
        memory: editedAgent.memory,
        recent_events: editedAgent.recent_events,
      };

      await agentService.updateAgent(agent.id, updateData);
      onUpdate();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update agent');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!onDelete) return;
    if (!confirm(`Delete agent "${agent.name}"? This action cannot be undone.`)) return;

    try {
      setIsDeleting(true);
      setError(null);
      await onDelete(agent.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete agent');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div ref={modalRef} className="modal-container max-w-3xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="sticky top-0 bg-gradient-to-r from-emerald-600 to-cyan-600 p-4 sm:p-6 rounded-t-lg sm:rounded-t-xl z-10">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
              <div className="relative group flex-shrink-0">
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleProfilePicChange}
                  className="hidden"
                  id="profile-pic-input"
                />
                <label
                  htmlFor="profile-pic-input"
                  className="cursor-pointer block w-12 h-12 sm:w-14 sm:h-14 rounded-full overflow-hidden border-2 border-white/30 hover:border-white/60 active:border-white transition-all touch-manipulation"
                  title="Click to change profile picture"
                >
                  {editedAgent.profile_pic ? (
                    <img
                      src={
                        editedAgent.profile_pic.startsWith('data:')
                          ? editedAgent.profile_pic
                          : getAgentProfilePicUrl(editedAgent, 128) || ''
                      }
                      alt={agent.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full bg-white/20 flex items-center justify-center">
                      <span className="text-white text-lg sm:text-xl font-bold">
                        {agent.name[0]?.toUpperCase()}
                      </span>
                    </div>
                  )}
                </label>
                {editedAgent.profile_pic && (
                  <button
                    onClick={handleRemoveProfilePic}
                    className="absolute -top-1 -right-1 w-6 h-6 sm:w-5 sm:h-5 bg-red-500 rounded-full text-white flex items-center justify-center hover:bg-red-600 active:bg-red-700 transition-colors opacity-100 sm:opacity-0 sm:group-hover:opacity-100 touch-manipulation"
                    title="Remove profile picture"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
              <div className="min-w-0">
                <h2 className="text-lg sm:text-2xl font-bold text-white truncate">{agent.name}</h2>
                <p className="text-emerald-100 text-xs sm:text-sm">Agent Profile</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-white hover:bg-white/20 active:bg-white/30 p-2 rounded-lg transition-colors flex-shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center touch-manipulation"
            >
              <svg className="w-5 h-5 sm:w-6 sm:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
          {/* Config File (Read-only) */}
          {agent.config_file && (
            <div>
              <label className="block text-xs sm:text-sm font-semibold text-slate-700 mb-1.5 sm:mb-2">
                Config File
              </label>
              <div className="px-3 sm:px-4 py-2 sm:py-3 bg-slate-100 border border-slate-200 rounded-lg text-xs sm:text-sm text-slate-600 break-all">
                {agent.config_file}
              </div>
            </div>
          )}

          {/* In a Nutshell */}
          <div>
            <label className="block text-xs sm:text-sm font-semibold text-slate-700 mb-1.5 sm:mb-2">
              In a Nutshell
            </label>
            <textarea
              value={editedAgent.in_a_nutshell || ''}
              onChange={(e) =>
                setEditedAgent({ ...editedAgent, in_a_nutshell: e.target.value })
              }
              className="w-full px-3 sm:px-4 py-2 sm:py-3 border border-slate-300 rounded-lg text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent resize-none"
              rows={3}
              placeholder="Brief identity summary..."
            />
          </div>

          {/* Characteristics */}
          <div>
            <label className="block text-xs sm:text-sm font-semibold text-slate-700 mb-1.5 sm:mb-2">
              Characteristics
            </label>
            <textarea
              value={editedAgent.characteristics || ''}
              onChange={(e) =>
                setEditedAgent({ ...editedAgent, characteristics: e.target.value })
              }
              className="w-full px-3 sm:px-4 py-2 sm:py-3 border border-slate-300 rounded-lg text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent resize-none"
              rows={4}
              placeholder="Personality traits, communication style..."
            />
          </div>

          {/* Backgrounds */}
          <div>
            <label className="block text-xs sm:text-sm font-semibold text-slate-700 mb-1.5 sm:mb-2">
              Backgrounds
            </label>
            <textarea
              value={editedAgent.backgrounds || ''}
              onChange={(e) =>
                setEditedAgent({ ...editedAgent, backgrounds: e.target.value })
              }
              className="w-full px-3 sm:px-4 py-2 sm:py-3 border border-slate-300 rounded-lg text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent resize-none"
              rows={4}
              placeholder="Backstory, history, experience..."
            />
          </div>

          {/* Memory */}
          <div>
            <label className="block text-xs sm:text-sm font-semibold text-slate-700 mb-1.5 sm:mb-2">
              Memory
            </label>
            <textarea
              value={editedAgent.memory || ''}
              onChange={(e) => setEditedAgent({ ...editedAgent, memory: e.target.value })}
              className="w-full px-3 sm:px-4 py-2 sm:py-3 border border-slate-300 rounded-lg text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent resize-none"
              rows={4}
              placeholder="Medium-term memory..."
            />
          </div>

          {/* Recent Events */}
          <div>
            <label className="block text-xs sm:text-sm font-semibold text-slate-700 mb-1.5 sm:mb-2">
              Recent Events
            </label>
            <textarea
              value={editedAgent.recent_events || ''}
              onChange={(e) =>
                setEditedAgent({ ...editedAgent, recent_events: e.target.value })
              }
              className="w-full px-3 sm:px-4 py-2 sm:py-3 border border-slate-300 rounded-lg text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent resize-none"
              rows={3}
              placeholder="Short-term recent context..."
            />
          </div>

          {/* Current System Prompt (Read-only) */}
          <div>
            <label className="block text-xs sm:text-sm font-semibold text-slate-700 mb-1.5 sm:mb-2">
              Current System Prompt (Read-only)
            </label>
            <textarea
              value={editedAgent.system_prompt}
              readOnly
              className="w-full px-3 sm:px-4 py-2 sm:py-3 border border-slate-200 rounded-lg text-xs sm:text-sm bg-slate-50 text-slate-600 resize-none"
              rows={5}
            />
          </div>

          {/* Created At */}
          <div>
            <label className="block text-xs sm:text-sm font-semibold text-slate-700 mb-1.5 sm:mb-2">
              Created At
            </label>
            <div className="px-3 sm:px-4 py-2 sm:py-3 bg-slate-100 border border-slate-200 rounded-lg text-xs sm:text-sm text-slate-600">
              {new Date(agent.created_at).toLocaleString()}
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="text-red-600 text-xs sm:text-sm bg-red-50 border border-red-200 rounded-lg px-3 sm:px-4 py-2 sm:py-3">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-slate-50 p-4 sm:p-6 rounded-b-lg sm:rounded-b-xl border-t border-slate-200 flex flex-col sm:flex-row justify-between gap-2 sm:gap-3">
          {/* Delete button - admin only */}
          {isAdmin && onDelete && (
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="w-full sm:w-auto px-4 sm:px-6 py-2.5 sm:py-3 bg-white border border-red-300 text-red-600 rounded-lg hover:bg-red-50 active:bg-red-100 disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed font-medium transition-colors text-sm sm:text-base min-h-[44px] touch-manipulation flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
              {isDeleting ? 'Deleting...' : 'Delete'}
            </button>
          )}
          {/* Spacer when no delete button */}
          {!(isAdmin && onDelete) && <div />}
          <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
            <button
              onClick={onClose}
              className="w-full sm:w-auto px-4 sm:px-6 py-2.5 sm:py-3 bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 active:bg-slate-200 font-medium transition-colors text-sm sm:text-base min-h-[44px] touch-manipulation"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="w-full sm:w-auto px-4 sm:px-6 py-2.5 sm:py-3 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 active:bg-emerald-800 disabled:bg-slate-300 disabled:cursor-not-allowed font-medium transition-colors shadow-sm hover:shadow-md text-sm sm:text-base min-h-[44px] touch-manipulation"
            >
              {isSaving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
