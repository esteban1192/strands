import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import React, { useState } from 'react';
import './MarkdownRenderer.css';

interface MarkdownRendererProps {
  content: string;
}

function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button className="md-code-copy" onClick={handleCopy} title="Copy code">
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="md-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre({ children, ...props }: React.HTMLAttributes<HTMLPreElement>) {
            // Extract raw text from the code element for the copy button
            const codeEl = Array.isArray(children) ? children[0] : children;
            let rawCode = '';
            if (codeEl && typeof codeEl === 'object' && 'props' in codeEl) {
              const extractText = (node: unknown): string => {
                if (typeof node === 'string') return node;
                if (Array.isArray(node)) return node.map(extractText).join('');
                if (node && typeof node === 'object' && 'props' in node) {
                  return extractText((node as { props: { children?: unknown } }).props.children);
                }
                return '';
              };
              rawCode = extractText(codeEl.props.children);
            }
            return (
              <div className="md-code-block">
                <CopyButton code={rawCode} />
                <pre {...props}>{children}</pre>
              </div>
            );
          },
          a({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
