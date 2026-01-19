import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Agent, AgentCreate, AgentConfig } from '../../types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

interface CreateAgentFormProps {
  availableConfigs: AgentConfig;
  onCreateAgent: (agentData: AgentCreate) => Promise<Agent>;
  onClose: () => void;
}

export const CreateAgentForm = ({
  availableConfigs,
  onCreateAgent,
  onClose,
}: CreateAgentFormProps) => {
  const { t } = useTranslation('agents');
  const [createMode, setCreateMode] = useState<'config' | 'custom'>('config');
  const [newAgent, setNewAgent] = useState({
    name: '',
    config_file: '',
    in_a_nutshell: '',
    characteristics: '',
    backgrounds: '',
    memory: '',
    recent_events: '',
  });
  const [agentError, setAgentError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAgent.name.trim()) return;

    try {
      setAgentError(null);
      const agentData = createMode === 'config'
        ? { name: newAgent.name, config_file: newAgent.config_file }
        : {
            name: newAgent.name,
            in_a_nutshell: newAgent.in_a_nutshell || null,
            characteristics: newAgent.characteristics || null,
            backgrounds: newAgent.backgrounds || null,
            memory: newAgent.memory || null,
            recent_events: newAgent.recent_events || null,
          };

      await onCreateAgent(agentData);
      setNewAgent({
        name: '',
        config_file: '',
        in_a_nutshell: '',
        characteristics: '',
        backgrounds: '',
        memory: '',
        recent_events: '',
      });
      onClose();
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : 'Failed to create agent');
    }
  };

  return (
    <div className="p-3 sm:p-4 border-b border-border bg-muted/50">
      <div className="flex gap-2 mb-3">
        <Button
          type="button"
          onClick={() => setCreateMode('config')}
          variant={createMode === 'config' ? 'default' : 'outline'}
          size="sm"
          className={cn(
            "flex-1",
            createMode === 'config' && "bg-emerald-600 hover:bg-emerald-700"
          )}
        >
          {t('configFile')}
        </Button>
        <Button
          type="button"
          onClick={() => setCreateMode('custom')}
          variant={createMode === 'custom' ? 'default' : 'outline'}
          size="sm"
          className={cn(
            "flex-1",
            createMode === 'custom' && "bg-emerald-600 hover:bg-emerald-700"
          )}
        >
          {t('custom')}
        </Button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <Input
          type="text"
          value={newAgent.name}
          onChange={(e) => {
            setNewAgent({ ...newAgent, name: e.target.value });
            setAgentError(null);
          }}
          placeholder={t('agentName')}
          autoFocus
        />

        {createMode === 'config' ? (
          <>
            <select
              value={newAgent.config_file}
              onChange={(e) => setNewAgent({ ...newAgent, config_file: e.target.value })}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm"
              required
            >
              <option value="">{t('selectConfigFile')}</option>
              {Object.entries(availableConfigs).map(([name, path]) => (
                <option key={name} value={path}>
                  {name}
                </option>
              ))}
            </select>
            {Object.keys(availableConfigs).length === 0 && (
              <div className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
                {t('noConfigFiles')}
              </div>
            )}
          </>
        ) : (
          <div className="space-y-2">
            <Textarea
              value={newAgent.in_a_nutshell}
              onChange={(e) => setNewAgent({ ...newAgent, in_a_nutshell: e.target.value })}
              placeholder={t('inANutshellDesc')}
              className="h-16 sm:h-20 resize-none"
            />
            <Textarea
              value={newAgent.characteristics}
              onChange={(e) => setNewAgent({ ...newAgent, characteristics: e.target.value })}
              placeholder={t('characteristicsDesc')}
              className="h-16 sm:h-20 resize-none"
            />
          </div>
        )}

        {agentError && (
          <div className="text-destructive text-xs sm:text-sm bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {agentError}
          </div>
        )}

        <Button
          type="submit"
          className="w-full bg-green-600 hover:bg-green-700"
        >
          {t('createAgent')}
        </Button>
      </form>
    </div>
  );
};
