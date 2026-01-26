import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useFocusTrap } from '../hooks/useFocusTrap';

interface HowToDocsModalProps {
  onClose: () => void;
}

type TabId = 'getting-started' | 'agents' | 'usage';

export const HowToDocsModal = ({ onClose }: HowToDocsModalProps) => {
  const { t } = useTranslation('docs');
  const [activeTab, setActiveTab] = useState<TabId>('getting-started');
  const modalRef = useFocusTrap<HTMLDivElement>(true);

  const tabs = [
    {
      id: 'getting-started' as TabId,
      label: t('tabs.gettingStarted'),
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
    {
      id: 'agents' as TabId,
      label: t('tabs.agentConfig'),
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ),
    },
    {
      id: 'usage' as TabId,
      label: t('tabs.appUsage'),
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      ),
    },
  ];

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

  return (
    <div className="modal-overlay">
      <div ref={modalRef} className="modal-container max-w-4xl">
        {/* Header */}
        <div className="modal-header">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 sm:w-6 sm:h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <div className="min-w-0">
                <h2 className="text-lg sm:text-2xl font-bold text-white truncate">{t('title')}</h2>
                <p className="text-slate-200 text-xs sm:text-sm">{t('subtitle')}</p>
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

          {/* Tabs */}
          <div className="flex gap-1 mt-4 bg-white/10 rounded-lg p-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 flex items-center justify-center gap-1.5 px-2 sm:px-4 py-2 rounded-md text-xs sm:text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'bg-white text-slate-700'
                    : 'text-white/80 hover:text-white hover:bg-white/10'
                }`}
              >
                {tab.icon}
                <span className="hidden sm:inline">{tab.label}</span>
                <span className="sm:hidden">{tab.label.split(' ')[0]}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {activeTab === 'getting-started' && <GettingStartedContent />}
          {activeTab === 'agents' && <AgentConfigContent />}
          {activeTab === 'usage' && <AppUsageContent />}
        </div>

        {/* Footer */}
        <div className="modal-footer flex justify-end">
          <button
            onClick={onClose}
            className="btn-primary px-4 sm:px-6 py-2.5 sm:py-3 text-sm sm:text-base min-h-[44px] touch-manipulation"
          >
            {t('gotIt')}
          </button>
        </div>
      </div>
    </div>
  );
};

// Section component for consistent styling
const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="mb-6 last:mb-0">
    <h3 className="text-base sm:text-lg font-semibold text-slate-800 mb-3 flex items-center gap-2">
      <span className="w-1.5 h-1.5 rounded-full bg-slate-600"></span>
      {title}
    </h3>
    <div className="text-sm text-slate-600 leading-relaxed">{children}</div>
  </div>
);

// Code block component
const CodeBlock = ({ children }: { children: React.ReactNode }) => (
  <pre className="bg-slate-100 border border-slate-200 rounded-lg p-3 text-xs sm:text-sm overflow-x-auto my-2">
    <code className="text-slate-700">{children}</code>
  </pre>
);

// Inline code component
const Code = ({ children }: { children: React.ReactNode }) => (
  <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs sm:text-sm text-slate-700 font-mono">
    {children}
  </code>
);

// List item with bullet
const Li = ({ children }: { children: React.ReactNode }) => (
  <li className="flex items-start gap-2 mb-2">
    <span className="text-slate-400 mt-1.5">•</span>
    <span>{children}</span>
  </li>
);

const GettingStartedContent = () => {
  const { t } = useTranslation('docs');

  return (
    <div className="space-y-6">
      <Section title={t('gettingStarted.whatIsTitle')}>
        <p className="mb-3">
          {t('gettingStarted.whatIsDesc')}
        </p>
      </Section>

      <Section title={t('gettingStarted.quickStartTitle')}>
        <ul className="list-none">
          <Li><strong>Create a Room:</strong> {t('gettingStarted.createRoom')}</Li>
          <Li><strong>Add Agents:</strong> {t('gettingStarted.addAgents')}</Li>
          <Li><strong>Start Chatting:</strong> {t('gettingStarted.startChatting')}</Li>
          <Li><strong>Manage Agents:</strong> {t('gettingStarted.manageAgents')}</Li>
        </ul>
      </Section>

      <Section title={t('gettingStarted.keyConcepts')}>
        <ul className="list-none">
          <Li><strong>Agents:</strong> {t('gettingStarted.conceptAgents')}</Li>
          <Li><strong>Rooms:</strong> {t('gettingStarted.conceptRooms')}</Li>
          <Li><strong>Third-Person Format:</strong> {t('gettingStarted.conceptThirdPerson')}</Li>
        </ul>
      </Section>
    </div>
  );
};

const AgentConfigContent = () => {
  const { t } = useTranslation('docs');

  return (
    <div className="space-y-6">
      <Section title={t('agentConfig.folderStructure')}>
        <p className="mb-3">{t('agentConfig.folderDesc')}</p>
        <CodeBlock>{`agents/
  agent_name/
    ├── in_a_nutshell.md      # Brief identity summary
    ├── characteristics.md     # Personality traits
    ├── recent_events.md      # Auto-updated from conversations
    ├── consolidated_memory.md # Long-term memories (optional)
    └── profile.png           # Profile picture (optional)`}</CodeBlock>
      </Section>

      <Section title={t('agentConfig.requiredFiles')}>
        <ul className="list-none">
          <Li>
            <strong>in_a_nutshell.md:</strong> {t('agentConfig.inANutshellDesc')}
          </Li>
          <Li>
            <strong>characteristics.md:</strong> {t('agentConfig.characteristicsDesc')}
          </Li>
        </ul>
      </Section>

      <Section title={t('agentConfig.thirdPersonTitle')}>
        <p className="mb-3">
          {t('agentConfig.thirdPersonDesc')}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
            <p className="text-green-800 font-medium text-xs mb-1">{t('agentConfig.correct')}</p>
            <p className="text-green-700 text-xs">{t('agentConfig.correctExample')}</p>
          </div>
          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-red-800 font-medium text-xs mb-1">{t('agentConfig.wrong')}</p>
            <p className="text-red-700 text-xs">{t('agentConfig.wrongExample')}</p>
          </div>
        </div>
      </Section>

      <Section title={t('agentConfig.profilePictures')}>
        <p className="mb-2">
          {t('agentConfig.profilePicturesDesc')} <Code>png</Code>, <Code>jpg</Code>, <Code>jpeg</Code>, <Code>gif</Code>, <Code>webp</Code>, <Code>svg</Code>
        </p>
        <p>{t('agentConfig.commonFileNames')} <Code>profile.*</Code>, <Code>avatar.*</Code>, <Code>picture.*</Code>, <Code>photo.*</Code></p>
      </Section>

      <Section title={t('agentConfig.groupConfig')}>
        <p className="mb-3">
          {t('agentConfig.groupConfigDesc')}
        </p>
        <CodeBlock>{`agents/
  group_steinsgate/
    ├── group_config.yaml  # Shared tool overrides
    ├── okabe/
    │   ├── in_a_nutshell.md
    │   └── characteristics.md
    └── kurisu/
        ├── in_a_nutshell.md
        └── characteristics.md`}</CodeBlock>
      </Section>

      <Section title={t('agentConfig.creatingAgent')}>
        <ol className="list-decimal list-inside space-y-2">
          <li>{t('agentConfig.step1')}</li>
          <li>{t('agentConfig.step2')}</li>
          <li>{t('agentConfig.step3')}</li>
          <li>{t('agentConfig.step4')}</li>
          <li>{t('agentConfig.step5')}</li>
        </ol>
      </Section>
    </div>
  );
};

const AppUsageContent = () => {
  const { t } = useTranslation('docs');

  return (
    <div className="space-y-6">
      <Section title={t('appUsage.creatingRooms')}>
        <ul className="list-none">
          <Li>{t('appUsage.creatingRoomsSteps.click')}</Li>
          <Li>{t('appUsage.creatingRoomsSteps.enter')}</Li>
          <Li>{t('appUsage.creatingRoomsSteps.created')}</Li>
          <Li>{t('appUsage.creatingRoomsSteps.rename')}</Li>
        </ul>
      </Section>

      <Section title={t('appUsage.addingAgents')}>
        <ul className="list-none">
          <Li>{t('appUsage.addingAgentsSteps.open')}</Li>
          <Li>{t('appUsage.addingAgentsSteps.browse')}</Li>
          <Li>{t('appUsage.addingAgentsSteps.added')}</Li>
          <Li>{t('appUsage.addingAgentsSteps.remove')}</Li>
        </ul>
      </Section>

      <Section title={t('appUsage.chatting')}>
        <ul className="list-none">
          <Li>{t('appUsage.chattingSteps.type')}</Li>
          <Li>{t('appUsage.chattingSteps.send')}</Li>
          <Li>{t('appUsage.chattingSteps.respond')}</Li>
          <Li>{t('appUsage.chattingSteps.thinking')}</Li>
          <Li>{t('appUsage.chattingSteps.multiple')}</Li>
        </ul>
      </Section>

      <Section title={t('appUsage.specialMessages')}>
        <p className="mb-3">{t('appUsage.specialMessagesDesc')}</p>
        <ul className="list-none">
          <Li><Code>[scene]</Code> / <Code>[상황]</Code> - {t('appUsage.scenePrefix').replace('[scene] or [상황] - ', '').replace('[scene] 또는 [상황] - ', '')}</Li>
          <Li><Code>[ooc]</Code> / <Code>[괄호]</Code> - {t('appUsage.oocPrefix').replace('[ooc] or [괄호] - ', '').replace('[ooc] 또는 [괄호] - ', '')}</Li>
          <Li>{t('appUsage.regularMessages')}</Li>
        </ul>
      </Section>

      <Section title={t('appUsage.managingProfiles')}>
        <ul className="list-none">
          <Li>{t('appUsage.managingProfilesSteps.goTo')}</Li>
          <Li>{t('appUsage.managingProfilesSteps.click')}</Li>
          <Li>{t('appUsage.managingProfilesSteps.edit')}</Li>
          <Li>{t('appUsage.managingProfilesSteps.upload')}</Li>
          <Li>{t('appUsage.managingProfilesSteps.saved')}</Li>
        </ul>
      </Section>

      <Section title={t('appUsage.searchNav')}>
        <ul className="list-none">
          <Li>{t('appUsage.searchNavSteps.search')}</Li>
          <Li>{t('appUsage.searchNavSteps.korean')}</Li>
          <Li>{t('appUsage.searchNavSteps.hamburger')}</Li>
          <Li>{t('appUsage.searchNavSteps.mobile')}</Li>
        </ul>
      </Section>

      <Section title={t('appUsage.keyboardShortcuts')}>
        <ul className="list-none">
          <Li><Code>Escape</Code> - {t('appUsage.shortcuts.escape').replace('Escape - ', '')}</Li>
          <Li><Code>Enter</Code> - {t('appUsage.shortcuts.enter').replace('Enter - ', '')}</Li>
          <Li><Code>Shift + Enter</Code> - {t('appUsage.shortcuts.shiftEnter').replace('Shift + Enter - ', '')}</Li>
        </ul>
      </Section>
    </div>
  );
};
