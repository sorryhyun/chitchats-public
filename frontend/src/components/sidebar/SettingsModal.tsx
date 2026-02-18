import { useTranslation } from 'react-i18next';
import { Modal, ModalHeader, ModalContent, ModalFooter } from '../ui/modal';
import { Toggle } from '../ui/toggle';
import { StatusIndicator, StatusType } from '../ui/status-indicator';
import { useVoice } from '../../contexts/VoiceContext';
import { useThinkingPreference } from '../../hooks/useThinkingPreference';
import { useExcusePreference } from '../../hooks/useExcusePreference';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal = ({ isOpen, onClose }: SettingsModalProps) => {
  const { t } = useTranslation('sidebar');

  const { enabled: voiceEnabled, setEnabled: setVoiceEnabled, serverAvailable } = useVoice();

  const {
    expandedByDefault: thinkingExpandedByDefault,
    setExpandedByDefault: setThinkingExpandedByDefault,
  } = useThinkingPreference();

  const {
    showExcuse,
    setShowExcuse,
  } = useExcusePreference();

  const getVoiceStatus = (): StatusType => {
    if (!voiceEnabled) return 'disabled';
    if (serverAvailable) return 'available';
    return 'unavailable';
  };

  const getVoiceStatusText = () => {
    if (!voiceEnabled) return t('voiceDisabled', 'Disabled');
    if (serverAvailable) return t('voiceReady', 'Ready');
    return t('voiceUnavailable', 'Unavailable');
  };

  const settingsIcon = (
    <svg
      className="w-5 h-5 sm:w-6 sm:h-6 text-white"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
      />
    </svg>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <ModalHeader
        onClose={onClose}
        icon={settingsIcon}
        title={t('settings', 'Settings')}
        subtitle={t('settingsDescription', 'Configure app options')}
      />

      <ModalContent className="space-y-6">
        {/* Voice Server Section */}
        <div className="bg-slate-50 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <svg
                className="w-5 h-5 text-slate-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                />
              </svg>
              <span className="font-medium text-slate-700">
                {t('voiceGeneration', 'Voice Generation')}
              </span>
            </div>
            <Toggle checked={voiceEnabled} onCheckedChange={setVoiceEnabled} />
          </div>

          <StatusIndicator status={getVoiceStatus()} text={getVoiceStatusText()} />

          <p className="mt-3 text-xs text-slate-500">
            {t(
              'voiceHelpText',
              'Enable TTS voice synthesis for agent messages. Requires voice server running on port 8002.'
            )}
          </p>
        </div>

        {/* Thinking Process Section */}
        <div className="bg-slate-50 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <svg
                className="w-5 h-5 text-slate-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                />
              </svg>
              <span className="font-medium text-slate-700">
                {t('thinkingProcess', 'Thinking Process')}
              </span>
            </div>
            <Toggle
              checked={thinkingExpandedByDefault}
              onCheckedChange={setThinkingExpandedByDefault}
            />
          </div>

          <StatusIndicator
            status={thinkingExpandedByDefault ? 'available' : 'disabled'}
            text={
              thinkingExpandedByDefault
                ? t('thinkingExpanded', 'Expanded by default')
                : t('thinkingCollapsed', 'Collapsed by default')
            }
          />

          <p className="mt-3 text-xs text-slate-500">
            {t(
              'thinkingHelpText',
              'When enabled, agent thinking process will be expanded by default for all messages.'
            )}
          </p>
        </div>
        {/* Show Excuse Section */}
        <div className="bg-slate-50 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <svg
                className="w-5 h-5 text-slate-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span className="font-medium text-slate-700">
                {t('showExcuse', 'Show Excuse')}
              </span>
            </div>
            <Toggle checked={showExcuse} onCheckedChange={setShowExcuse} />
          </div>

          <StatusIndicator
            status={showExcuse ? 'available' : 'disabled'}
            text={
              showExcuse
                ? t('excuseVisible', 'Visible')
                : t('excuseHidden', 'Hidden')
            }
          />

          <p className="mt-3 text-xs text-slate-500">
            {t(
              'excuseHelpText',
              'Show or hide the inner reaction (excuse) that agents record before composing their outward response. The excuse tool is always provided to agents regardless of this setting.'
            )}
          </p>
        </div>
      </ModalContent>

      <ModalFooter>
        <button
          onClick={onClose}
          className="btn-primary w-full px-4 sm:px-6 py-2.5 sm:py-3 text-sm sm:text-base min-h-[44px] touch-manipulation"
        >
          {t('close', 'Close')}
        </button>
      </ModalFooter>
    </Modal>
  );
};
