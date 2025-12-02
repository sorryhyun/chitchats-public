import { useState, useEffect, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { Button } from '@/components/ui/button';
import { X, Loader2, BookOpen, Sparkles, MessageSquare, Settings2, Lightbulb, Languages } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HowToUseModalProps {
  onClose: () => void;
}

type Language = 'en' | 'ko';

const sectionIcons: Record<string, React.ReactNode> = {
  // English
  'Getting Started': <Sparkles className="w-5 h-5" />,
  'Sending Messages': <MessageSquare className="w-5 h-5" />,
  'Room Controls': <Settings2 className="w-5 h-5" />,
  'Managing Agents': <BookOpen className="w-5 h-5" />,
  'Tips for Great Roleplay': <Lightbulb className="w-5 h-5" />,
  // Korean
  '시작하기': <Sparkles className="w-5 h-5" />,
  '메시지 보내기': <MessageSquare className="w-5 h-5" />,
  '방 컨트롤': <Settings2 className="w-5 h-5" />,
  '에이전트 관리': <BookOpen className="w-5 h-5" />,
  '좋은 롤플레이를 위한 팁': <Lightbulb className="w-5 h-5" />,
};

const detectBrowserLanguage = (): Language => {
  const lang = navigator.language || navigator.languages?.[0] || 'en';
  return lang.startsWith('ko') ? 'ko' : 'en';
};

export const HowToUseModal = ({ onClose }: HowToUseModalProps) => {
  const [language, setLanguage] = useState<Language>(detectBrowserLanguage);
  const [content, setContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const modalRef = useFocusTrap<HTMLDivElement>(true);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const fetchContent = useCallback(async (lang: Language) => {
    setIsLoading(true);
    setError(null);
    try {
      const file = lang === 'ko' ? '/how_to_use.ko.md' : '/how_to_use.md';
      const response = await fetch(file);
      if (!response.ok) {
        throw new Error('Failed to load guide');
      }
      const text = await response.text();
      setContent(text);
    } catch (err) {
      setError(lang === 'ko'
        ? '가이드를 불러올 수 없습니다. 다시 시도해주세요.'
        : 'Could not load the guide. Please try again.');
      console.error('Failed to fetch how to use guide:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchContent(language);
  }, [language, fetchContent]);

  const toggleLanguage = () => {
    setLanguage(prev => prev === 'en' ? 'ko' : 'en');
  };

  const markdownComponents = useMemo(() => ({
    h1: ({ children }: { children?: React.ReactNode }) => (
      <h1 className="text-2xl font-bold text-foreground mb-2 pb-3 border-b border-border">
        {children}
      </h1>
    ),
    h2: ({ children }: { children?: React.ReactNode }) => {
      const text = String(children);
      const icon = sectionIcons[text];
      return (
        <h2 className="flex items-center gap-2.5 text-lg font-semibold text-foreground mt-8 mb-4 pb-2 border-b border-border/50">
          {icon && <span className="text-accent">{icon}</span>}
          {children}
        </h2>
      );
    },
    h3: ({ children }: { children?: React.ReactNode }) => (
      <h3 className="text-base font-semibold text-foreground mt-5 mb-2">
        {children}
      </h3>
    ),
    p: ({ children }: { children?: React.ReactNode }) => (
      <p className="text-foreground/80 leading-relaxed mb-3">
        {children}
      </p>
    ),
    ul: ({ children }: { children?: React.ReactNode }) => (
      <ul className="space-y-1.5 mb-4 ml-1">
        {children}
      </ul>
    ),
    ol: ({ children }: { children?: React.ReactNode }) => (
      <ol className="space-y-1.5 mb-4 ml-1 list-decimal list-inside">
        {children}
      </ol>
    ),
    li: ({ children }: { children?: React.ReactNode }) => (
      <li className="text-foreground/80 leading-relaxed flex gap-2">
        <span className="text-accent mt-1.5">•</span>
        <span className="flex-1">{children}</span>
      </li>
    ),
    table: ({ children }: { children?: React.ReactNode }) => (
      <div className="my-4 rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }: { children?: React.ReactNode }) => (
      <thead className="bg-muted/50">
        {children}
      </thead>
    ),
    th: ({ children }: { children?: React.ReactNode }) => (
      <th className="px-4 py-2.5 text-left font-semibold text-foreground border-b border-border">
        {children}
      </th>
    ),
    td: ({ children }: { children?: React.ReactNode }) => (
      <td className="px-4 py-2.5 text-foreground/80 border-b border-border/50 last:border-b-0">
        {children}
      </td>
    ),
    tr: ({ children }: { children?: React.ReactNode }) => (
      <tr className="hover:bg-muted/30 transition-colors">
        {children}
      </tr>
    ),
    code: ({ className, children }: { className?: string; children?: React.ReactNode }) => {
      const isBlock = className?.includes('language-');
      if (isBlock) {
        return (
          <code className="block text-sm">
            {children}
          </code>
        );
      }
      return (
        <code className="px-1.5 py-0.5 rounded bg-muted text-accent text-sm font-mono">
          {children}
        </code>
      );
    },
    pre: ({ children }: { children?: React.ReactNode }) => (
      <pre className="my-4 p-4 rounded-lg bg-muted/50 border border-border overflow-x-auto font-mono text-sm">
        {children}
      </pre>
    ),
    blockquote: ({ children }: { children?: React.ReactNode }) => (
      <blockquote className="my-4 pl-4 border-l-2 border-accent/50 text-foreground/70 italic">
        {children}
      </blockquote>
    ),
    hr: () => (
      <hr className="my-6 border-border/50" />
    ),
    strong: ({ children }: { children?: React.ReactNode }) => (
      <strong className="font-semibold text-foreground">
        {children}
      </strong>
    ),
  }), []);

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={modalRef}
        className={cn(
          "bg-card rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col",
          "border border-border/50 overflow-hidden"
        )}
      >
        {/* Header */}
        <div className="relative flex items-center justify-between px-6 py-4 border-b border-border bg-gradient-to-r from-accent/5 to-transparent">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-accent/10">
              <BookOpen className="w-5 h-5 text-accent" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-foreground">
                {language === 'ko' ? '사용법' : 'How to Use'}
              </h2>
              <p className="text-xs text-muted-foreground">
                {language === 'ko' ? 'Claude Code RP 시작하기' : 'Get started with Claude Code RP'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              onClick={toggleLanguage}
              variant="ghost"
              size="sm"
              className="h-8 px-2 gap-1.5 text-muted-foreground hover:text-foreground"
            >
              <Languages className="w-4 h-4" />
              <span className="text-xs font-medium">{language === 'ko' ? 'EN' : '한국어'}</span>
            </Button>
            <Button
              onClick={onClose}
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full hover:bg-destructive/10 hover:text-destructive"
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 overflow-auto">
          <div className="px-6 py-5">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Loader2 className="w-8 h-8 animate-spin text-accent" />
                <p className="text-sm text-muted-foreground">
                  {language === 'ko' ? '가이드 불러오는 중...' : 'Loading guide...'}
                </p>
              </div>
            ) : error ? (
              <div className="text-center py-16">
                <p className="text-destructive">{error}</p>
              </div>
            ) : (
              <div className="max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents}
                >
                  {content || ''}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
