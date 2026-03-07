export interface Chat {
  id: string;
  agent_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export type ChatMessageType = 'text' | 'tool_call' | 'tool_result';

export interface ChatToolCall {
  id: string;
  message_id: string;
  tool_use_id: string;
  tool_name: string;
  input: unknown;
  created_at: string;
}

export interface ChatToolResult {
  id: string;
  message_id: string;
  tool_use_id: string;
  status: 'success' | 'error';
  result: unknown;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  agent_id: string | null;
  role: 'user' | 'assistant';
  message_type: ChatMessageType;
  content: import('./agent').ContentBlock;
  ordinal: number;
  is_approved: boolean;
  created_at: string;
  tool_call: ChatToolCall | null;
  tool_result: ChatToolResult | null;
}

export interface ChatDetail {
  id: string;
  agent_id: string;
  title: string | null;
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface ChatSendMessageResponse {
  chat_id: string;
  response: string;
  messages: ChatMessage[];
}

export interface ChatAcceptedResponse {
  chat_id: string;
  status: 'processing';
}

export interface ChatSSEEvent {
  type: 'thinking' | 'complete' | 'error';
  response?: string;
  messages?: ChatMessage[];
  message?: string;
}
