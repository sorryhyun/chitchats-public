import { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';

type SetupStep = 'welcome' | 'password' | 'username' | 'complete';

interface SetupWizardProps {
  onComplete: () => void;
}

export function SetupWizard({ onComplete }: SetupWizardProps) {
  const [step, setStep] = useState<SetupStep>('welcome');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [userName, setUserName] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleNext = async () => {
    setError('');

    switch (step) {
      case 'welcome':
        setStep('password');
        break;

      case 'password':
        if (password.length < 4) {
          setError('Password must be at least 4 characters');
          return;
        }
        if (password !== confirmPassword) {
          setError('Passwords do not match');
          return;
        }
        setStep('username');
        break;

      case 'username':
        setIsLoading(true);
        try {
          await invoke('create_env_file', {
            config: {
              password,
              user_name: userName || 'User',
            },
          });
          setStep('complete');
        } catch (e) {
          setError(`Failed to create configuration: ${e}`);
        } finally {
          setIsLoading(false);
        }
        break;

      case 'complete':
        // Start the backend and transition to main app
        try {
          await invoke('start_backend');
          // Wait for backend to be healthy
          let healthy = false;
          for (let i = 0; i < 30; i++) {
            healthy = await invoke('check_backend_health');
            if (healthy) break;
            await new Promise((resolve) => setTimeout(resolve, 500));
          }
          if (!healthy) {
            setError('Backend failed to start. Please restart the application.');
            return;
          }
          onComplete();
        } catch (e) {
          setError(`Failed to start backend: ${e}`);
        }
        break;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full">
        {/* Progress indicator */}
        <div className="flex justify-center mb-8">
          <div className="flex items-center space-x-2">
            {['welcome', 'password', 'username', 'complete'].map((s, i) => (
              <div key={s} className="flex items-center">
                <div
                  className={`w-3 h-3 rounded-full transition-colors ${
                    ['welcome', 'password', 'username', 'complete'].indexOf(step) >= i
                      ? 'bg-indigo-500'
                      : 'bg-gray-300'
                  }`}
                />
                {i < 3 && (
                  <div
                    className={`w-8 h-0.5 transition-colors ${
                      ['welcome', 'password', 'username', 'complete'].indexOf(step) > i
                        ? 'bg-indigo-500'
                        : 'bg-gray-300'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Step content */}
        {step === 'welcome' && (
          <div className="text-center">
            <div className="text-6xl mb-4">&#128172;</div>
            <h1 className="text-2xl font-bold text-gray-800 mb-4">
              Welcome to ChitChats
            </h1>
            <p className="text-gray-600 mb-8">
              A multi-Claude chat room where AI agents with unique personalities
              interact in real-time conversations.
            </p>
            <p className="text-sm text-gray-500 mb-8">
              Let's set up your application in just a few steps.
            </p>
          </div>
        )}

        {step === 'password' && (
          <div>
            <h2 className="text-xl font-bold text-gray-800 mb-2 text-center">
              Create a Password
            </h2>
            <p className="text-gray-600 mb-6 text-center text-sm">
              This password will be used to log into the application.
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  placeholder="Enter password"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Confirm Password
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  placeholder="Confirm password"
                  onKeyDown={(e) => e.key === 'Enter' && handleNext()}
                />
              </div>
              {password && password.length < 8 && (
                <p className="text-yellow-600 text-sm">
                  Tip: Passwords with 8+ characters are more secure
                </p>
              )}
            </div>
          </div>
        )}

        {step === 'username' && (
          <div>
            <h2 className="text-xl font-bold text-gray-800 mb-2 text-center">
              Choose Your Display Name
            </h2>
            <p className="text-gray-600 mb-6 text-center text-sm">
              This name will appear when you send messages in chat rooms.
            </p>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Display Name
              </label>
              <input
                type="text"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                placeholder="User"
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && handleNext()}
              />
              <p className="text-gray-500 text-sm mt-2">
                Leave empty to use "User" as default
              </p>
            </div>
          </div>
        )}

        {step === 'complete' && (
          <div className="text-center">
            <div className="text-6xl mb-4">&#10003;</div>
            <h2 className="text-xl font-bold text-gray-800 mb-4">
              Setup Complete!
            </h2>
            <p className="text-gray-600 mb-8">
              Your configuration has been saved. Click the button below to start
              using ChitChats.
            </p>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="mt-4 p-3 bg-red-100 border border-red-300 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Navigation button */}
        <button
          onClick={handleNext}
          disabled={isLoading}
          className="mt-8 w-full bg-indigo-500 hover:bg-indigo-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <span className="flex items-center justify-center">
              <svg
                className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Setting up...
            </span>
          ) : step === 'complete' ? (
            'Launch ChitChats'
          ) : (
            'Continue'
          )}
        </button>
      </div>
    </div>
  );
}
