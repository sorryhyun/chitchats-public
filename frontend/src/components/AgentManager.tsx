import { useState, useEffect, useMemo, memo } from 'react';
import { useTranslation } from 'react-i18next';
import { agentService } from '../services/agentService';
import type { Agent } from '../types';
import { AgentAvatar } from './AgentAvatar';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { useAgentContext } from '../contexts/AgentContext';
import { koreanSearch } from '../utils/koreanSearch';

interface AgentManagerProps {
  roomId: number;
}

export const AgentManager = memo(({ roomId }: AgentManagerProps) => {
  const { t } = useTranslation('agents');
  const { t: tCommon } = useTranslation('common');
  const { isAdmin } = useAuth();
  const { addToast } = useToast();
  const { viewProfile } = useAgentContext();
  const [roomAgents, setRoomAgents] = useState<Agent[]>([]);
  const [allAgents, setAllAgents] = useState<Agent[]>([]);
  const [showAddAgent, setShowAddAgent] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchRoomAgents = async () => {
      try {
        const data = await agentService.getRoomAgents(roomId);
        setRoomAgents(data);
      } catch {
        addToast(t('unableToLoadRoom'), 'error');
      }
    };

    const fetchAllAgents = async () => {
      try {
        const data = await agentService.getAllAgents();
        setAllAgents(data);
      } catch {
        addToast(t('unableToLoadAgents'), 'error');
      }
    };

    if (roomId) {
      fetchRoomAgents();
      fetchAllAgents();
    }
  }, [roomId, addToast, t]);

  const fetchRoomAgents = async () => {
    try {
      const data = await agentService.getRoomAgents(roomId);
      setRoomAgents(data);
    } catch {
      addToast(t('unableToLoadRoom'), 'error');
    }
  };

  const handleAddAgent = async (agentId: number) => {
    try {
      await agentService.addAgentToRoom(roomId, agentId);
      fetchRoomAgents();
      addToast(t('agentAdded'), 'success');
    } catch (err) {
      console.error('Failed to add agent to room:', err);
      addToast(t('failedToAddAgent'), 'error');
    }
  };

  const handleRemoveAgent = async (agentId: number) => {
    try {
      await agentService.removeAgentFromRoom(roomId, agentId);
      fetchRoomAgents();
      addToast(t('agentRemoved'), 'success');
    } catch (err) {
      console.error('Failed to remove agent from room:', err);
      addToast(t('failedToRemoveAgent'), 'error');
    }
  };

  // Memoized agent filtering with O(1) lookup using Set (supports Korean consonant search)
  const roomAgentIds = useMemo(() => new Set(roomAgents.map(a => a.id)), [roomAgents]);

  const filteredAvailableAgents = useMemo(() => {
    return allAgents
      .filter(agent => !roomAgentIds.has(agent.id))
      .filter(agent => koreanSearch(agent.name, searchTerm));
  }, [allAgents, roomAgentIds, searchTerm]);


  return (
    <div className="h-full flex flex-col p-4 select-none">
      <div className="flex-shrink-0 mb-4 space-y-3">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
          <h3 className="font-bold text-lg text-slate-700">{t('roomAgents')}</h3>
          <span className="ml-auto text-sm font-medium text-slate-600">({roomAgents.length})</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={t('searchByName')}
              className="w-full pl-10 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            <svg className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35m0 0A7.5 7.5 0 104.5 4.5a7.5 7.5 0 0012.15 12.15z" />
            </svg>
          </div>
          <button
            onClick={() => setSearchTerm('')}
            className="px-3 py-2 bg-slate-100 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-200"
          >
            {tCommon('clear')}
          </button>
        </div>
        <button
          onClick={() => setShowAddAgent(!showAddAgent)}
          className="w-full px-4 py-2.5 bg-slate-700 text-white rounded-lg hover:bg-slate-600 text-sm font-medium transition-colors flex items-center justify-center gap-2"
        >
          <span>{showAddAgent ? '−' : '+'}</span>
          {showAddAgent ? tCommon('cancel') : t('addToRoom')}
        </button>
      </div>

      {/* Scrollable content area */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="space-y-2">
        {roomAgents.length === 0 ? (
          <div className="text-center py-8">
            <svg className="w-12 h-12 mx-auto text-slate-300 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
            <p className="text-sm text-slate-500">{t('noAgentsInRoom')}</p>
            <p className="text-xs text-slate-500 mt-1">{t('addOneToStart')}</p>
          </div>
        ) : (
          roomAgents.map((agent) => (
            <div
              key={agent.id}
              onClick={() => viewProfile(agent)}
              className="group px-4 py-3 bg-white border border-slate-300 rounded-lg text-sm font-medium hover:bg-gradient-to-r hover:from-emerald-50 hover:to-cyan-50 hover:border-emerald-300 hover:shadow-sm transition-all flex items-center gap-3 cursor-pointer"
            >
              <AgentAvatar agent={agent} size="md" />
              <span className="text-slate-700 group-hover:text-emerald-800 truncate flex-1 min-w-0">{agent.name}</span>
              {isAdmin && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(t('removeConfirm', { name: agent.name }))) {
                      handleRemoveAgent(agent.id);
                    }
                  }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 hover:bg-red-100 rounded text-red-500 hover:text-red-700"
                  title={t('removeFromRoom')}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          ))
        )}
        </div>

        {(showAddAgent || searchTerm) && (
        <div className="mt-4 p-4 bg-white rounded-lg border border-slate-300 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <h4 className="text-sm font-semibold text-slate-700">{t('availableAgents')}</h4>
            <span className="text-xs text-slate-600">({filteredAvailableAgents.length})</span>
          </div>
          {filteredAvailableAgents.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-4">
              {t('allAgentsInRoom')}
            </p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {filteredAvailableAgents.map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => handleAddAgent(agent.id)}
                  className="w-full px-3 py-2 bg-slate-50 hover:bg-emerald-50 border border-slate-300 hover:border-emerald-300 rounded-lg text-sm font-medium text-slate-700 hover:text-emerald-800 transition-all flex items-center gap-3"
                >
                  <AgentAvatar agent={agent} size="sm" />
                  <span className="truncate">{agent.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );
});
