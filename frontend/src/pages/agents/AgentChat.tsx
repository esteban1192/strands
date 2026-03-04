import { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useApi } from '@/hooks';
import { agentApi } from '@/api';
import { LoadingSpinner, ErrorMessage } from '@/components/common';
import type { AgentMessage } from '@/types';
import './AgentChat.css';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  /** Full Strands message trace for this turn (assistant only) */
  trace?: AgentMessage[];
}

/** Extract tool-call and tool-result pairs from a Strands message trace. */
function extractToolSteps(messages: AgentMessage[]) {
  const steps: Array<{
    name: string;
    input: Record<string, unknown>;
    output: string;
    status: string;
  }> = [];

  // Build a map of toolUseId -> tool call info
  const callMap = new Map<string, { name: string; input: Record<string, unknown> }>();

  for (const msg of messages) {
    if (!msg.content) continue;
    for (const block of msg.content) {
      if (block.toolUse) {
        callMap.set(block.toolUse.toolUseId, {
          name: block.toolUse.name,
          input: block.toolUse.input,
        });
      }
      if (block.toolResult) {
        const call = callMap.get(block.toolResult.toolUseId);
        const outputParts: string[] = [];
        for (const c of block.toolResult.content || []) {
          if (c.text) outputParts.push(c.text);
          if (c.json) outputParts.push(JSON.stringify(c.json, null, 2));
        }
        steps.push({
          name: call?.name ?? 'unknown_tool',
          input: call?.input ?? {},
          output: outputParts.join('\n'),
          status: block.toolResult.status ?? 'success',
        });
      }
    }
  }
  return steps;
}

/** Extract final assistant text blocks from the last assistant message. */
function extractFinalText(messages: AgentMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role !== 'assistant') continue;
    const texts: string[] = [];
    for (const block of msg.content || []) {
      if (block.text) texts.push(block.text);
    }
    if (texts.length > 0) return texts.join('\n');
  }
  return '';
}

function ToolStep({ step }: {
  step: { name: string; input: Record<string, unknown>; output: string; status: string };
}) {
  const [expanded, setExpanded] = useState(false);
  const inputStr = JSON.stringify(step.input, null, 2);
  const hasLongOutput = step.output.length > 300;

  return (
    <div className={`tool-step tool-step--${step.status}`}>
      <button
        className="tool-step__header"
        onClick={() => setExpanded((v) => !v)}
        title={expanded ? 'Collapse' : 'Expand'}
      >
        <span className="tool-step__icon">{step.status === 'error' ? '✗' : '✓'}</span>
        <span className="tool-step__name">{step.name}</span>
        <span className="tool-step__toggle">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="tool-step__body">
          <div className="tool-step__section">
            <span className="tool-step__label">Input</span>
            <pre className="tool-step__code">{inputStr}</pre>
          </div>
          <div className="tool-step__section">
            <span className="tool-step__label">Output</span>
            <pre className="tool-step__code">{step.output || '(empty)'}</pre>
          </div>
        </div>
      )}

      {!expanded && step.output && (
        <div className="tool-step__preview">
          {hasLongOutput ? step.output.slice(0, 200) + '…' : step.output}
        </div>
      )}
    </div>
  );
}

function AssistantMessage({
  msg,
  agentName,
}: {
  msg: ChatMessage;
  agentName: string;
}) {
  const trace = msg.trace ?? [];
  const toolSteps = extractToolSteps(trace);
  const finalText = trace.length > 0 ? extractFinalText(trace) : msg.content;

  return (
    <div className="chat-message chat-message--assistant">
      <span className="chat-message__role">{agentName}</span>

      {toolSteps.length > 0 && (
        <div className="chat-message__tools">
          <span className="chat-message__tools-label">
            Tool calls ({toolSteps.length})
          </span>
          {toolSteps.map((step, i) => (
            <ToolStep key={i} step={step} />
          ))}
        </div>
      )}

      <div className="chat-message__bubble">{finalText}</div>
    </div>
  );
}

export default function AgentChat() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: agent, loading, error: loadError } = useApi(() => agentApi.getById(id!), [id]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
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

    const userMessage: ChatMessage = { role: 'user', content: prompt };
    setMessages((prev) => [...prev, userMessage]);
    setSending(true);

    try {
      const result = await agentApi.invoke(id, prompt);
      const traceMessages: AgentMessage[] = result.messages ?? [];
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: result.response,
        trace: traceMessages,
      };
      setMessages((prev) => [...prev, assistantMessage]);
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

        {messages.map((msg, i) =>
          msg.role === 'user' ? (
            <div key={i} className="chat-message chat-message--user">
              <span className="chat-message__role">You</span>
              <div className="chat-message__bubble">{msg.content}</div>
            </div>
          ) : (
            <AssistantMessage key={i} msg={msg} agentName={agent.name} />
          ),
        )}

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
