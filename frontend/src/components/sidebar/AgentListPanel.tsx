import { useState, useMemo } from 'react';
import type { Agent } from '../../types';
import { AgentAvatar } from '../AgentAvatar';

type Provider = 'claude' | 'codex';

interface AgentListPanelProps {
  agents: Agent[];
  selectedAgentId: number | null;
  onSelectAgent: (agentId: number, provider: Provider) => void;
  onViewProfile: (agent: Agent) => void;
}

export const AgentListPanel = ({
  agents,
  selectedAgentId,
  onSelectAgent,
  onViewProfile,
}: AgentListPanelProps) => {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  // Group agents by their group field, memoized to avoid recomputation
  const groupedAgents = useMemo(() => {
    const groups = new Map<string, Agent[]>();

    agents.forEach((agent) => {
      const groupName = agent.group || 'Ungrouped';
      if (!groups.has(groupName)) {
        groups.set(groupName, []);
      }
      groups.get(groupName)!.push(agent);
    });

    // Sort groups: Ungrouped last, others alphabetically (Korean-aware)
    return Array.from(groups.entries()).sort(([a], [b]) => {
      if (a === 'Ungrouped') return 1;
      if (b === 'Ungrouped') return -1;
      return a.localeCompare(b, 'ko-KR', { sensitivity: 'base' });
    });
  }, [agents]);

  const toggleGroup = (groupName: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) {
        next.delete(groupName);
      } else {
        next.add(groupName);
      }
      return next;
    });
  };

  const renderAgent = (agent: Agent) => (
    <div
      key={agent.id}
      onClick={() => onViewProfile(agent)}
      className={`group relative flex items-center gap-2.5 sm:gap-3 p-2.5 sm:p-3 rounded-lg cursor-pointer transition-all min-h-[52px] touch-manipulation ${
        selectedAgentId === agent.id
          ? 'bg-slate-100 border border-slate-300'
          : 'hover:bg-slate-50 active:bg-slate-100'
      }`}
    >
      <AgentAvatar
        agent={agent}
        size="md"
        className={`flex-shrink-0 w-10 h-10 sm:w-11 sm:h-11 ${
          selectedAgentId === agent.id
            ? 'ring-2 ring-slate-400'
            : 'group-hover:ring-2 group-hover:ring-slate-300'
        }`}
      />
      {/* Agent name */}
      <span
        className={`font-medium truncate text-sm sm:text-base flex-1 min-w-0 ${
          selectedAgentId === agent.id ? 'text-slate-800' : 'text-slate-700'
        }`}
      >
        {agent.name}
      </span>
      {/* Action buttons - always visible */}
      <div className="flex gap-1 flex-shrink-0">
        {/* Codex button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSelectAgent(agent.id, 'codex');
          }}
          className="p-2 hover:bg-green-100 active:bg-green-200 rounded text-green-600 hover:text-green-700 min-w-[40px] min-h-[40px] flex items-center justify-center touch-manipulation font-bold text-sm"
          title="Chat with Codex"
        >
          x
        </button>
        {/* Claude button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSelectAgent(agent.id, 'claude');
          }}
          className="p-2 hover:bg-orange-100 active:bg-orange-200 rounded text-orange-600 hover:text-orange-700 min-w-[40px] min-h-[40px] flex items-center justify-center touch-manipulation font-bold text-sm"
          title="Chat with Claude Code"
        >
          c
        </button>
      </div>
    </div>
  );

  return (
    <div className="absolute inset-0 overflow-y-auto p-2 sm:p-3 divide-y-2 divide-slate-400">
      {agents.length === 0 ? (
        <div className="text-center text-slate-500 mt-8 px-4">
          <p className="text-xs sm:text-sm">No agents yet</p>
          <p className="text-xs mt-1">Create one to get started!</p>
        </div>
      ) : (
        groupedAgents.map(([groupName, groupAgents]) => {
          const isCollapsed = collapsedGroups.has(groupName);
          return (
            <div key={groupName}>
              {/* Group Header */}
              <button
                onClick={() => toggleGroup(groupName)}
                className="w-full flex items-center justify-between px-3 py-2 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 rounded-lg transition-colors group/header"
              >
                <div className="flex items-center gap-2">
                  <svg
                    className={`w-4 h-4 text-slate-600 transition-transform ${
                      isCollapsed ? '-rotate-90' : ''
                    }`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                  <span className="font-semibold text-sm text-slate-700">
                    {groupName}
                  </span>
                  <span className="text-xs text-slate-600 bg-slate-200 px-2 py-0.5 rounded-full">
                    {groupAgents.length}
                  </span>
                </div>
              </button>

              {/* Group Agents */}
              {!isCollapsed && (
                <div className="pl-2 divide-y divide-slate-300">
                  {groupAgents.map(renderAgent)}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
};
