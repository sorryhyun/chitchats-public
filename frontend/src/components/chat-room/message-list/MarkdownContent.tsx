import { memo, lazy, Suspense } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

const LazyHighlighter = lazy(() =>
  Promise.all([
    import('react-syntax-highlighter'),
    import('react-syntax-highlighter/dist/esm/styles/prism'),
  ]).then(([mod, styles]) => ({
    default: (props: any) => (
      <mod.Prism style={styles.oneDark} {...props} />
    ),
  }))
);

const CodeFallback = ({ children }: { children: string }) => (
  <pre className="bg-slate-800 text-slate-200 p-4 rounded-xl text-sm font-mono overflow-x-auto">
    <code>{children}</code>
  </pre>
);

interface MarkdownContentProps {
  content: string;
}

export const MarkdownContent = memo(({ content }: MarkdownContentProps) => (
  <ReactMarkdown
    remarkPlugins={[remarkGfm, remarkBreaks]}
    components={{
      p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
      strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
      em: ({ children }) => <em className="italic">{children}</em>,
      ul: ({ children }) => <ul className="list-disc list-inside mb-2">{children}</ul>,
      ol: ({ children }) => <ol className="list-decimal list-inside mb-2">{children}</ol>,
      li: ({ children }) => <li className="mb-1">{children}</li>,
      code: ({ inline, className, children, ...props }: any) => {
        const match = /language-(\w+)/.exec(className || '');
        const codeString = String(children).replace(/\n$/, '');
        const isInline = inline ?? (!className && !codeString.includes('\n'));

        return isInline ? (
          <code className="bg-slate-200 text-slate-800 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
            {children}
          </code>
        ) : (
          <Suspense fallback={<CodeFallback>{codeString}</CodeFallback>}>
            <LazyHighlighter
              language={match ? match[1] : 'text'}
              PreTag="div"
              customStyle={{
                margin: 0,
                borderRadius: '0.75rem',
                fontSize: '0.875rem',
              }}
              {...props}
            >
              {codeString}
            </LazyHighlighter>
          </Suspense>
        );
      },
      pre: ({ children }) => (
        <div className="mb-2 overflow-hidden rounded-xl">
          {children}
        </div>
      ),
    }}
  >
    {content}
  </ReactMarkdown>
));
