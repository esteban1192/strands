import { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useApi } from '@/hooks';
import { agentApi, chatApi } from '@/api';
import { LoadingSpinner, ErrorMessage } from '@/components/common';
import type { ContentBlock, ChatMessage, Chat } from '@/types';
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
/*  Render a single chat message (one content block per row)          */
/* ------------------------------------------------------------------ */
function MessageBubble({ msg, agentName }: { msg: ChatMessage; agentName: string }) {
  const block = msg.content;
  // For tool_result messages (role="user" in Strands), display as assistant
  const displayRole = msg.message_type === 'tool_result' ? 'assistant' : msg.role;

  return (
    <div className={`chat-message chat-message--${displayRole}`}>
      <span className="chat-message__role">{displayRole === 'user' ? 'You' : agentName}</span>
      <div className="chat-message__bubble">
        {isTextBlock(block) && <TextContent text={block.text} />}
        {isToolUseBlock(block) && (
          <ToolUseContent name={block.toolUse.name} input={block.toolUse.input} />
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
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingChat, setLoadingChat] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, scrollToBottom]);

  // Load chat list for this agent
  useEffect(() => {
    if (!id) return;
    chatApi.listByAgent(id).then(setChatList).catch(() => {});
  }, [id, chatId]);

  // If a chatId is present (from URL or state), load its messages
  useEffect(() => {
    if (!id || !chatId) return;
    setLoadingChat(true);
    chatApi
      .getById(id, chatId)
      .then((detail) => {
        setMessages(detail.messages);
      })
      .catch(() => {
        setError('Failed to load chat history');
        setChatId(null);
      })
      .finally(() => setLoadingChat(false));
  }, [id, chatId]);

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
    const optimisticMsg: ChatMessage = {
      id: crypto.randomUUID(),
      chat_id: chatId ?? '',
      role: 'user',
      message_type: 'text',
      content: { text: prompt },
      ordinal: messages.length,
      created_at: new Date().toISOString(),
      tool_call: null,
      tool_result: null,
    };
    setMessages((prev) => [...prev, optimisticMsg]);
    setSending(true);

    try {
      let result;
      if (!chatId) {
        // First message — create a new chat
        result = await chatApi.create(id, prompt);
        setChatId(result.chat_id);
        setSearchParams({ chatId: result.chat_id }, { replace: true });
      } else {
        // Follow-up message — send to existing chat
        result = await chatApi.sendMessage(id, chatId, prompt);
      }

      // Replace with the authoritative server messages
      setMessages(result.messages);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to get response';
      setError(message);
      // Remove optimistic message on error
      setMessages((prev) => prev.filter((m) => m.id !== optimisticMsg.id));
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

  const handleNewChat = () => {
    setChatId(null);
    setMessages([]);
    setError(null);
    setSearchParams({}, { replace: true });
  };

  const handleSelectChat = (selectedChatId: string) => {
    setChatId(selectedChatId);
    setMessages([]);
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
        <button className="chat-new-btn" onClick={handleNewChat} title="New chat">
          + New Chat
        </button>
      </div>

      <div className="chat-layout">
        {/* Sidebar with chat history */}
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

            {!loadingChat && messages.length === 0 && !sending && (
              <div className="chat-messages-empty">
                Send a message to start chatting with {agent.name}
              </div>
            )}

            {messages.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} agentName={agent.name} />
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
      </div>
    </div>
  );
}
