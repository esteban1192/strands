import { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useApi } from '@/hooks';
import { agentApi } from '@/api';
import { LoadingSpinner, ErrorMessage } from '@/components/common';
import type { AgentMessage, ContentBlock } from '@/types';
import './AgentChat.css';

/* ------------------------------------------------------------------ */
/*  Helpers to identify content-block shapes                          */
/* ------------------------------------------------------------------ */
function isTextBlock(b: ContentBlock): b is { text: string } {
  return typeof (b as Record<string, unknown>).text === 'string';
}

function isToolUseBlock(b: ContentBlock): b is { toolUse: { toolUseId: string; name: string; input: unknown } } {
  return !!(b as Record<string, unknown>).toolUse;
}

function isToolResultBlock(
  b: ContentBlock,
): b is { toolResult: { toolUseId: string; content: { text?: string }[]; status: 'success' | 'error' } } {
  return !!(b as Record<string, unknown>).toolResult;
}

/* ------------------------------------------------------------------ */
/*  Small sub-components for rendering each content-block type        */
/* ------------------------------------------------------------------ */

function TextContent({ text }: { text: string }) {
  return <span className="chat-text">{text}</span>;
}

function ToolUseContent({ name, input }: { name: string; input: unknown }) {
  const [open, setOpen] = useState(false);
  const inputStr = typeof input === 'string' ? input : JSON.stringify(input, null, 2);

  return (
    <div className="chat-tool-use">
      <button className="chat-tool-use__header" onClick={() => setOpen((v) => !v)}>
        <span className="chat-tool-use__icon">&#9881;</span>
        <span className="chat-tool-use__name">{name}</span>
        <span className="chat-tool-use__toggle">{open ? '▾' : '▸'}</span>
      </button>
      {open && <pre className="chat-tool-use__input">{inputStr}</pre>}
    </div>
  );
}

function ToolResultContent({ content, status }: { content: { text?: string }[]; status: string }) {
  const [open, setOpen] = useState(false);
  const text = content
    .map((c) => c.text ?? '')
    .filter(Boolean)
    .join('\n');

  if (!text) return null;

  // Show a short preview (first 120 chars) when collapsed
  const preview = text.length > 120 ? text.slice(0, 120) + '…' : text;

  return (
    <div className={`chat-tool-result chat-tool-result--${status}`}>
      <button className="chat-tool-result__header" onClick={() => setOpen((v) => !v)}>
        <span className="chat-tool-result__status">{status === 'success' ? '✓' : '✗'}</span>
        <span className="chat-tool-result__label">Tool result</span>
        <span className="chat-tool-result__toggle">{open ? '▾' : '▸'}</span>
      </button>
      <pre className="chat-tool-result__body">{open ? text : preview}</pre>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Render a single agent message (may contain many content blocks)   */
/* ------------------------------------------------------------------ */
function MessageBubble({ msg, agentName }: { msg: AgentMessage; agentName: string }) {
  return (
    <div className={`chat-message chat-message--${msg.role}`}>
      <span className="chat-message__role">{msg.role === 'user' ? 'You' : agentName}</span>
      <div className="chat-message__bubble">
        {msg.content.map((block, i) => {
          if (isTextBlock(block)) return <TextContent key={i} text={block.text} />;
          if (isToolUseBlock(block))
            return <ToolUseContent key={i} name={block.toolUse.name} input={block.toolUse.input} />;
          if (isToolResultBlock(block))
            return (
              <ToolResultContent key={i} content={block.toolResult.content} status={block.toolResult.status} />
            );
          return null;
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Chat component                                               */
/* ------------------------------------------------------------------ */
export default function AgentChat() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: agent, loading, error: loadError } = useApi(() => agentApi.getById(id!), [id]);

  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, scrollToBottom]);

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  };

  const handleSend = async () => {
    const prompt = input.trim();
    if (!prompt || sending || !id) return;

    setInput('');
    setError(null);
    if (inputRef.current) inputRef.current.style.height = 'auto';

    // Optimistic user bubble
    const userMessage: AgentMessage = { role: 'user', content: [{ text: prompt }] };
    setMessages((prev) => [...prev, userMessage]);
    setSending(true);

    try {
      const result = await agentApi.invoke(id, prompt);

      // Replace the whole conversation with the server's authoritative list
      // which includes every tool_use / tool_result block.
      if (result.messages && result.messages.length > 0) {
        setMessages(result.messages);
      } else {
        // Fallback: just append a plain text assistant bubble
        setMessages((prev) => [...prev, { role: 'assistant', content: [{ text: result.response }] }]);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to get response';
      setError(message);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (loading) return <LoadingSpinner />;
  if (loadError) return <ErrorMessage message={loadError} />;
  if (!agent) return <ErrorMessage message="Agent not found" />;

  return (
    <div className="chat-page">
      <div className="chat-header">
        <button className="chat-back-btn" onClick={() => navigate('/agents')} title="Back to agents">
          ←
        </button>
        <div>
          <h1>{agent.name}</h1>
          <p className="page-subtitle">{agent.model}</p>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && !sending && (
          <div className="chat-messages-empty">
            Send a message to start chatting with {agent.name}
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} agentName={agent.name} />
        ))}

        {sending && (
          <div className="chat-thinking">
            <div className="chat-thinking__dots">
              <span className="chat-thinking__dot" />
              <span className="chat-thinking__dot" />
              <span className="chat-thinking__dot" />
            </div>
            Thinking…
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {error && <div className="chat-error">{error}</div>}

      <div className="chat-input-area">
        <textarea
          ref={inputRef}
          className="chat-input"
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          disabled={sending}
          rows={1}
        />
        <button
          className="chat-send-btn"
          onClick={handleSend}
          disabled={sending || !input.trim()}
        >
          {sending ? 'Sending…' : 'Send'}
        </button>
      </div>
    </div>
  );
}
