import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../contexts/AuthContext';
import { useRoomContext } from '../../contexts/RoomContext';
import { useAgentContext } from '../../contexts/AgentContext';
import { useFetchAgentConfigs } from '../../hooks/useFetchAgentConfigs';
import { RoomListPanel } from './RoomListPanel';
import { CreateAgentForm } from './CreateAgentForm';
import { AgentListPanel } from './AgentListPanel';
import { ExportModal } from './ExportModal';
import { SettingsModal } from './SettingsModal';
import { koreanSearch } from '../../utils/koreanSearch';
import { LanguageSwitcher } from '../LanguageSwitcher';
import type { ProviderType } from '../../types';

type Provider = 'claude' | 'codex';

interface MainSidebarProps {
  onSelectRoom: (roomId: number) => void;
  onSelectAgent: (agentId: number, provider: Provider) => Promise<void>;
  onOpenDocs?: () => void;
}

export const MainSidebar = ({
  onSelectRoom,
  onSelectAgent,
  onOpenDocs,
}: MainSidebarProps) => {
  const { t } = useTranslation('sidebar');
  const { t: tCommon } = useTranslation('common');
  const { t: tRooms } = useTranslation('rooms');
  const { logout } = useAuth();
  const roomContext = useRoomContext();
  const agentContext = useAgentContext();
  const [activeTab, setActiveTab] = useState<'rooms' | 'agents'>('rooms');
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [agentSearchQuery, setAgentSearchQuery] = useState('');
  const [newRoomName, setNewRoomName] = useState('');
  const [showExportModal, setShowExportModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const { configs: availableConfigs, fetchConfigs } = useFetchAgentConfigs();

  // Create a new room with the specified provider
  const handleCreateRoom = async (provider: ProviderType) => {
    const trimmedName = newRoomName.trim();
    if (!trimmedName) return;

    try {
      const room = await roomContext.createRoom(trimmedName, provider);
      setNewRoomName('');
      onSelectRoom(room.id);
    } catch (err) {
      console.error('Failed to create room:', err);
    }
  };

  const handleShowAgentForm = () => {
    if (!showAgentForm) {
      fetchConfigs();
    }
    setShowAgentForm(!showAgentForm);
  };

  // Filter and sort agents (supports Korean consonant search)
  const filteredAndSortedAgents = agentContext.agents
    .filter(agent => koreanSearch(agent.name, agentSearchQuery))
    .sort((a, b) =>
      a.name.localeCompare(b.name, 'ko-KR', { sensitivity: 'base' })
    );

  return (
    <div className="w-80 sm:w-80 bg-slate-100 flex flex-col h-full border-r border-slate-300 select-none">
      {/* Header - Add left padding to avoid overlap with fixed hamburger button */}
      <div className="pl-14 pr-6 pt-2 pb-4 border-b border-slate-300 bg-white">
        <div className="flex items-center gap-2">
          <img src="/chitchats.webp" alt="ChitChats" className="w-8 h-8 rounded" />
          <div>
            <h2 className="text-mobile-base font-bold text-slate-700 tracking-tight">{tCommon('appName')}</h2>
            <p className="text-slate-600 text-xs font-medium tracking-wider">{tCommon('appSubtitle')}</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex bg-white">
        <button
          onClick={() => setActiveTab('rooms')}
          className={`flex-1 py-3 text-sm font-medium transition-colors ${
            activeTab === 'rooms'
              ? 'text-slate-700 border-b-2 border-slate-700'
              : 'text-slate-500 hover:text-slate-700 border-b-2 border-transparent'
          }`}
        >
          {t('chatrooms')}
        </button>
        <button
          onClick={() => setActiveTab('agents')}
          className={`flex-1 py-3 text-sm font-medium transition-colors ${
            activeTab === 'agents'
              ? 'text-slate-700 border-b-2 border-slate-700'
              : 'text-slate-500 hover:text-slate-700 border-b-2 border-transparent'
          }`}
        >
          {t('agents')}
        </button>
      </div>

      {/* Rooms Tab Content */}
      {activeTab === 'rooms' && (
        <>
          {/* New Room Input and Buttons */}
          <div className="p-3 border-b border-slate-300 bg-white space-y-2">
            <input
              type="text"
              value={newRoomName}
              onChange={(e) => setNewRoomName(e.target.value)}
              placeholder={tRooms('enterRoomName')}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-slate-400 transition-all"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newRoomName.trim()) {
                  handleCreateRoom('claude');
                }
              }}
            />
            <div className="flex gap-2">
              <button
                onClick={() => handleCreateRoom('claude')}
                disabled={!newRoomName.trim()}
                className="flex-1 px-3 py-2.5 bg-[#D97757] hover:bg-[#c96747] active:bg-[#b95737] text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 text-sm touch-manipulation min-h-[44px] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[#D97757]"
              >
                <span className="text-lg">+</span>
                Claude
              </button>
              <button
                onClick={() => handleCreateRoom('codex')}
                disabled={!newRoomName.trim()}
                className="flex-1 px-3 py-2.5 bg-[#10A37F] hover:bg-[#0d8a6a] active:bg-[#0a7155] text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 text-sm touch-manipulation min-h-[44px] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[#10A37F]"
              >
                <span className="text-lg">+</span>
                Codex
              </button>
            </div>
          </div>

          {/* Rooms List */}
          <div className="flex-1 min-h-0 relative">
            <RoomListPanel
              rooms={roomContext.rooms}
              selectedRoomId={roomContext.selectedRoomId}
              onSelectRoom={onSelectRoom}
              onDeleteRoom={roomContext.deleteRoom}
            />
          </div>
        </>
      )}

      {/* Agents Tab Content */}
      {activeTab === 'agents' && (
        <>
          {/* New Agent Button */}
          <div className="p-3 border-b border-slate-300 bg-white">
            <button
              onClick={handleShowAgentForm}
              className="w-full px-3 py-2.5 bg-slate-700 hover:bg-slate-600 active:bg-slate-500 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 text-sm touch-manipulation min-h-[44px]"
            >
              <span className="text-xl">+</span>
              {showAgentForm ? tCommon('cancel') : t('newAgent')}
            </button>
          </div>

          {/* Create Agent Form */}
          {showAgentForm && (
            <CreateAgentForm
              availableConfigs={availableConfigs}
              onCreateAgent={agentContext.createAgent}
              onClose={() => setShowAgentForm(false)}
            />
          )}

          {/* Search Agents */}
          <div className="p-3 border-b border-slate-300 bg-white">
            <div className="relative">
              <input
                type="text"
                value={agentSearchQuery}
                onChange={(e) => setAgentSearchQuery(e.target.value)}
                placeholder={t('searchAgents')}
                className="w-full px-3 py-2 pl-10 bg-slate-50 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-slate-400 transition-all"
              />
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              {agentSearchQuery && (
                <button
                  onClick={() => setAgentSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-700 transition-colors"
                  title={t('clearSearch')}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {/* Agents List */}
          <div className="flex-1 min-h-0 relative">
            <AgentListPanel
              agents={filteredAndSortedAgents}
              selectedAgentId={agentContext.selectedAgentId}
              onSelectAgent={onSelectAgent}
              onDeleteAgent={agentContext.deleteAgent}
              onViewProfile={agentContext.viewProfile}
            />
          </div>
        </>
      )}

      {/* Footer Buttons */}
      <div className="mt-auto p-3 border-t border-slate-300 bg-white space-y-2">
        {/* Language Switcher */}
        <LanguageSwitcher />

        {/* Export and Settings buttons in 2x2 grid */}
        <div className="grid grid-cols-2 gap-2">
          {/* Export Button */}
          <button
            onClick={() => setShowExportModal(true)}
            className="px-3 py-2.5 bg-slate-700 hover:bg-slate-600 active:bg-slate-500 text-white rounded-lg font-medium transition-colors text-sm touch-manipulation min-h-[44px] flex items-center justify-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            <span className="hidden sm:inline">{t('exportConversations')}</span>
          </button>

          {/* Settings Button */}
          <button
            onClick={() => setShowSettingsModal(true)}
            className="px-3 py-2.5 bg-slate-700 hover:bg-slate-600 active:bg-slate-500 text-white rounded-lg font-medium transition-colors text-sm touch-manipulation min-h-[44px] flex items-center justify-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span className="hidden sm:inline">{t('settings', 'Settings')}</span>
          </button>

          {/* Help Button */}
          {onOpenDocs && (
            <button
              onClick={onOpenDocs}
              className="px-3 py-2.5 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 text-slate-700 rounded-lg font-medium transition-colors text-sm touch-manipulation min-h-[44px] flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              <span className="hidden sm:inline">{t('howToUse')}</span>
            </button>
          )}

          {/* Logout Button */}
          <button
            onClick={() => {
              if (confirm(tCommon('logoutConfirm'))) {
                logout();
              }
            }}
            className="px-3 py-2.5 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 text-slate-700 rounded-lg font-medium transition-colors text-sm touch-manipulation min-h-[44px] flex items-center justify-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            <span className="hidden sm:inline">{tCommon('logout')}</span>
          </button>
        </div>
      </div>

      {/* Export Modal */}
      <ExportModal
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
      />
    </div>
  );
};
