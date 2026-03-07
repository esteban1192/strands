import { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useApi } from '@/hooks';
import { agentApi, chatApi, agentSubAgentApi } from '@/api';
import { LoadingSpinner, ErrorMessage, MarkdownRenderer } from '@/components/common';
import type { ContentBlock, ChatMessage, Chat, AgentSubAgent, ChatTask } from '@/types';
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

function TextContent({ text, isUser }: { text: string; isUser?: boolean }) {
  if (isUser) {
    return <span className="chat-text">{text}</span>;
  }
  return <MarkdownRenderer content={text} />;
}

function ToolUseContent({
  name,
  input,
  isPending,
  isChildActive,
  onApprove,
  onReject,
  isProcessing,
}: {
  name: string;
  input: unknown;
  isPending?: boolean;
  isChildActive?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
  isProcessing?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const inputStr = typeof input === 'string' ? input : JSON.stringify(input, null, 2);
  const isSubAgent = name.startsWith('invoke_agent_');
  const displayLabel = isSubAgent ? 'Agent delegation' : name;

  return (
    <div className={`chat-tool-use${isPending ? ' chat-tool-use--pending' : ''}${isSubAgent ? ' chat-tool-use--sub-agent' : ''}`}>
      <button className="chat-tool-use__header" onClick={() => setOpen((v) => !v)}>
        <span className="chat-tool-use__icon">{isSubAgent ? '🤖' : '⚙'}</span>
        <span className="chat-tool-use__name">{displayLabel}</span>
        {isPending && (
          <span className="chat-tool-use__badge">
            {isSubAgent ? 'Approve delegation' : 'Awaiting approval'}
          </span>
        )}
        {isChildActive && !isPending && (
          <span className="chat-tool-use__badge chat-tool-use__badge--active">
            Sub-agent working…
          </span>
        )}
        <span className="chat-tool-use__toggle">{open ? '▾' : '▸'}</span>
      </button>
      {open && <pre className="chat-tool-use__input">{inputStr}</pre>}
      {isPending && (
        <div className="chat-tool-use__actions">
          <button
            className="btn btn-primary btn-sm"
            onClick={onApprove}
            disabled={isProcessing}
          >
            {isProcessing ? 'Approving…' : '✓ Approve'}
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={onReject}
            disabled={isProcessing}
          >
            {isProcessing ? 'Rejecting…' : '✗ Reject'}
          </button>
        </div>
      )}
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
/*  Task table — inline display for background tasks                  */
/* ------------------------------------------------------------------ */

const TASK_STATUS_DISPLAY: Record<string, { icon: string; label: string; className: string }> = {
  pending:            { icon: '◦', label: 'Pending',    className: 'task-status--pending' },
  running:            { icon: '↻', label: 'Running',    className: 'task-status--running' },
  waiting_approval:   { icon: '⏸', label: 'Needs approval', className: 'task-status--approval' },
  completed:          { icon: '✓', label: 'Done',       className: 'task-status--completed' },
  failed:             { icon: '✗', label: 'Failed',     className: 'task-status--failed' },
  cancelled:          { icon: '—', label: 'Cancelled',  className: 'task-status--cancelled' },
};

function TaskStatusBadge({ status }: { status: string }) {
  const display = TASK_STATUS_DISPLAY[status] ?? { icon: '?', label: status, className: '' };
  return (
    <span className={`task-status-badge ${display.className}`}>
      <span className="task-status-badge__icon">{display.icon}</span>
      {display.label}
    </span>
  );
}

function TaskTable({
  tasks,
  onCancel,
  onTaskClick,
}: {
  tasks: ChatTask[];
  onCancel?: (taskId: string) => void;
  onTaskClick?: (task: ChatTask) => void;
}) {
  if (!tasks.length) return null;

  const canCancel = (t: ChatTask) =>
    t.status === 'pending' || t.status === 'running' || t.status === 'waiting_approval';

  return (
    <div className="task-table">
      <div className="task-table__header">
        <span className="task-table__title">Background Tasks</span>
        <span className="task-table__count">{tasks.length}</span>
      </div>
      <div className="task-table__body">
        {tasks.map((task) => (
          <div
            key={task.id}
            className={`task-table__row${task.chat_id ? ' task-table__row--clickable' : ''}`}
            onClick={() => task.chat_id && onTaskClick?.(task)}
          >
            <div className="task-table__instruction">{task.instruction}</div>
            <div className="task-table__right">
              <TaskStatusBadge status={task.status} />
              {canCancel(task) && onCancel && (
                <button
                  className="task-table__cancel-btn"
                  onClick={(e) => { e.stopPropagation(); onCancel(task.id); }}
                  title="Cancel task"
                >
                  ×
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Render a single chat message (one content block per row)          */
/* ------------------------------------------------------------------ */
function MessageBubble({
  msg,
  agentName,
  agentNameMap,
  parentAgentId,
  hasActiveChildDelegation,
  onApprove,
  onReject,
  isProcessing,
}: {
  msg: ChatMessage;
  agentName: string;
  agentNameMap: Record<string, string>;
  parentAgentId: string;
  hasActiveChildDelegation?: (toolName: string) => boolean;
  onApprove?: (messageId: string) => void;
  onReject?: (messageId: string) => void;
  isProcessing?: boolean;
}) {
  const block = msg.content;
  const displayRole = msg.message_type === 'tool_result' ? 'assistant' : msg.role;
  const isPending = msg.message_type === 'tool_call' && !msg.is_approved;

  const isSubAgentMsg = msg.agent_id != null && msg.agent_id !== parentAgentId;
  const resolvedName = displayRole === 'user'
    ? 'You'
    : (isSubAgentMsg && msg.agent_id ? (agentNameMap[msg.agent_id] ?? 'Sub-Agent') : agentName);

  return (
    <div className={`chat-message chat-message--${displayRole}${isSubAgentMsg ? ' chat-message--sub-agent' : ''}`}>
      <span className="chat-message__role">
        {resolvedName}
        {isSubAgentMsg && <span className="chat-message__sub-badge">sub-agent</span>}
      </span>
      <div className="chat-message__bubble">
        {isTextBlock(block) && <TextContent text={block.text} isUser={displayRole === 'user'} />}
        {isToolUseBlock(block) && (
          <ToolUseContent
            name={block.toolUse.name}
            input={block.toolUse.input}
            isPending={isPending}
            isChildActive={
              !isPending &&
              msg.is_approved &&
              block.toolUse.name.startsWith('invoke_agent_') &&
              hasActiveChildDelegation?.(block.toolUse.name)
            }
            onApprove={() => onApprove?.(msg.id)}
            onReject={() => onReject?.(msg.id)}
            isProcessing={isProcessing}
          />
        )}
        {isToolResultBlock(block) && (
          <ToolResultContent content={block.toolResult.content} status={block.toolResult.status} />
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Chat component                                               */
/* ------------------------------------------------------------------ */
export default function AgentChat() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { data: agent, loading, error: loadError } = useApi(() => agentApi.getById(id!), [id]);

  const [chatId, setChatId] = useState<string | null>(searchParams.get('chatId'));
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatList, setChatList] = useState<Chat[]>([]);
  const [subAgents, setSubAgents] = useState<AgentSubAgent[]>([]);
  const [input, setInput] = useState('');
  const [tasks, setTasks] = useState<ChatTask[]>([]);
  const [sourceChatId, setSourceChatId] = useState<string | null>(null);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingChat, setLoadingChat] = useState(false);
  const [processingApproval, setProcessingApproval] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, thinking, scrollToBottom]);

  // ---- SSE subscription for real-time agent results ----
  useEffect(() => {
    if (!id || !chatId) return;

    const url = chatApi.eventsUrl(id, chatId);
    const es = new EventSource(url);

    es.addEventListener('thinking', () => {
      setThinking(true);
    });

    es.addEventListener('complete', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.messages) {
          setMessages(data.messages);
        }
        if (data.tasks) {
          setTasks(data.tasks);
        }
      } catch {
        // Ignore malformed payloads
      }
      setThinking(false);
      setProcessingApproval(null);
      inputRef.current?.focus();
    });

    es.addEventListener('task_update', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.tasks) {
          setTasks(data.tasks);
        }
      } catch {
        // Ignore malformed payloads
      }
    });

    es.addEventListener('error', (e: Event) => {
      // SSE spec: "error" is both a named event and the reconnect signal.
      // Only surface our custom "error" events (MessageEvent with data).
      if (e instanceof MessageEvent && e.data) {
        try {
          const data = JSON.parse(e.data);
          setError(data.message || 'An error occurred');
        } catch {
          setError('An error occurred');
        }
        setThinking(false);
        setProcessingApproval(null);
      }
    });

    return () => {
      es.close();
    };
  }, [id, chatId]);

  // Load chat list for this agent
  useEffect(() => {
    if (!id) return;
    chatApi.listByAgent(id).then(setChatList).catch(() => {});
  }, [id, chatId]);

  // Load sub-agents so we can show their names on delegated messages
  useEffect(() => {
    if (!id) return;
    agentSubAgentApi.list(id).then(setSubAgents).catch(() => {});
  }, [id]);

  const hasActiveTasks = tasks.some(
    (t) => t.status === 'pending' || t.status === 'running' || t.status === 'waiting_approval',
  );

  const agentNameMap: Record<string, string> = {};
  for (const sa of subAgents) {
    agentNameMap[sa.child_agent_id] = sa.child_agent_name;
  }

  const hasActiveChildDelegation = useCallback(
    (toolName: string): boolean => {
      const sa = subAgents.find(
        (s) => `invoke_agent_${s.child_agent_name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}` === toolName
          || toolName.startsWith('invoke_agent_'),
      );
      if (!sa) return false;
      return messages.some(
        (m) =>
          m.agent_id === sa.child_agent_id &&
          m.message_type === 'tool_call' &&
          !m.is_approved,
      );
    },
    [subAgents, messages],
  );

  // Load messages and tasks when switching to an existing chat
  useEffect(() => {
    if (!id || !chatId) return;
    setLoadingChat(true);
    chatApi
      .getById(id, chatId)
      .then((detail) => {
        setMessages(detail.messages);
        setSourceChatId(detail.source_chat_id ?? null);
      })
      .catch(() => {
        setError('Failed to load chat history');
        setChatId(null);
      })
      .finally(() => setLoadingChat(false));

    chatApi.listTasks(id, chatId).then(setTasks).catch(() => {});
  }, [id, chatId]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  };

  const handleSend = async () => {
    const prompt = input.trim();
    if (!prompt || thinking || !id) return;

    setInput('');
    setError(null);
    if (inputRef.current) inputRef.current.style.height = 'auto';

    const optimisticMsg: ChatMessage = {
      id: crypto.randomUUID(),
      chat_id: chatId ?? '',
      agent_id: null,
      role: 'user',
      message_type: 'text',
      content: { text: prompt },
      ordinal: messages.length,
      is_approved: true,
      created_at: new Date().toISOString(),
      tool_call: null,
      tool_result: null,
    };
    setMessages((prev) => [...prev, optimisticMsg]);
    setThinking(true);

    try {
      if (!chatId) {
        const result = await chatApi.create(id, prompt);
        setChatId(result.chat_id);
        setSearchParams({ chatId: result.chat_id }, { replace: true });
        // SSE subscription will be established by the useEffect above
        // once chatId state updates.  The event_bus buffers the latest
        // event so we won't miss the result.
      } else {
        await chatApi.sendMessage(id, chatId, prompt);
        // Result arrives via SSE
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to send message';
      setError(message);
      setMessages((prev) => prev.filter((m) => m.id !== optimisticMsg.id));
      setThinking(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = () => {
    setChatId(null);
    setMessages([]);
    setTasks([]);
    setSourceChatId(null);
    setError(null);
    setThinking(false);
    setSearchParams({}, { replace: true });
  };

  const handleSelectChat = (selectedChatId: string) => {
    setChatId(selectedChatId);
    setMessages([]);
    setTasks([]);
    setSourceChatId(null);
    setThinking(false);
    setSearchParams({ chatId: selectedChatId }, { replace: true });
  };

  const handleDeleteChat = async (deleteChatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!id) return;
    try {
      await chatApi.delete(id, deleteChatId);
      setChatList((prev) => prev.filter((c) => c.id !== deleteChatId));
      if (chatId === deleteChatId) {
        handleNewChat();
      }
    } catch {
      setError('Failed to delete chat');
    }
  };

  const handleApproveToolCall = async (messageId: string) => {
    if (!id || !chatId) return;
    setProcessingApproval(messageId);
    setThinking(true);
    setError(null);
    try {
      await chatApi.approveToolCall(id, chatId, messageId);
      // Result arrives via SSE
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to approve tool call';
      setError(message);
      setThinking(false);
      setProcessingApproval(null);
    }
  };

  const handleCancelTask = async (taskId: string) => {
    try {
      await chatApi.cancelTask(taskId);
      if (id && chatId) {
        const updated = await chatApi.listTasks(id, chatId);
        setTasks(updated);
      }
    } catch {
      setError('Failed to cancel task');
    }
  };

  const handleRejectToolCall = async (messageId: string) => {
    if (!id || !chatId) return;
    setProcessingApproval(messageId);
    setThinking(true);
    setError(null);
    try {
      await chatApi.rejectToolCall(id, chatId, messageId);
      // Result arrives via SSE
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to reject tool call';
      setError(message);
      setThinking(false);
      setProcessingApproval(null);
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
        <div className="chat-header__actions">
          {sourceChatId && (
            <button
              className="chat-parent-btn"
              onClick={() => handleSelectChat(sourceChatId)}
              title="Go to parent chat"
            >
              ← Parent
            </button>
          )}
          <button className="chat-new-btn" onClick={handleNewChat} title="New chat">
            + New Chat
          </button>
        </div>
      </div>

      <div className="chat-layout">
        {chatList.length > 0 && (
          <aside className="chat-sidebar">
            <h3 className="chat-sidebar__title">History</h3>
            <ul className="chat-sidebar__list">
              {chatList.map((c) => (
                <li
                  key={c.id}
                  className={`chat-sidebar__item${c.id === chatId ? ' chat-sidebar__item--active' : ''}`}
                  onClick={() => handleSelectChat(c.id)}
                >
                  <span className="chat-sidebar__item-title">{c.title || 'Untitled'}</span>
                  <button
                    className="chat-sidebar__delete-btn"
                    onClick={(e) => handleDeleteChat(c.id, e)}
                    title="Delete chat"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </aside>
        )}

        <div className="chat-main">
          <div className="chat-messages">
            {loadingChat && <LoadingSpinner />}

            {!loadingChat && messages.length === 0 && !thinking && (
              <div className="chat-messages-empty">
                Send a message to start chatting with {agent.name}
              </div>
            )}

            {messages.map((msg) => {
              // Replace create_tasks tool calls and their results with the task table
              if (msg.message_type === 'tool_call' && msg.tool_call?.tool_name === 'create_tasks') {
                return (
                  <div key={msg.id} className="chat-message chat-message--assistant">
                    <span className="chat-message__role">{agent.name}</span>
                    <div className="chat-message__bubble">
                      <TaskTable
                        tasks={tasks}
                        onCancel={handleCancelTask}
                        onTaskClick={(task) => {
                          if (!task.chat_id) return;
                          if (task.agent_id === id) {
                            handleSelectChat(task.chat_id);
                          } else {
                            navigate(`/agents/${task.agent_id}/chat?chatId=${task.chat_id}`);
                          }
                        }}
                      />
                    </div>
                  </div>
                );
              }
              // Hide the tool_result for create_tasks (already shown in the table)
              if (
                msg.message_type === 'tool_result' &&
                msg.tool_result &&
                tasks.length > 0 &&
                tasks.some((t) => t.tool_use_id === msg.tool_result?.tool_use_id)
              ) {
                return null;
              }
              return (
                <MessageBubble
                  key={msg.id}
                  msg={msg}
                  agentName={agent.name}
                  agentNameMap={agentNameMap}
                  parentAgentId={agent.id}
                  hasActiveChildDelegation={hasActiveChildDelegation}
                  onApprove={handleApproveToolCall}
                  onReject={handleRejectToolCall}
                  isProcessing={processingApproval === msg.id}
                />
              );
            })}

            {thinking && (
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
            {hasActiveTasks && (
              <div className="chat-input-blocked">
                Tasks are running — waiting for completion…
              </div>
            )}
            <textarea
              ref={inputRef}
              className="chat-input"
              placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              disabled={thinking || hasActiveTasks}
              rows={1}
            />
            <button
              className="chat-send-btn"
              onClick={handleSend}
              disabled={thinking || hasActiveTasks || !input.trim()}
            >
              {thinking ? 'Sending…' : 'Send'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
