export interface Chat {
  id: string;
  agent_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: import('./agent').ContentBlock[];
  ordinal: number;
  created_at: string;
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
