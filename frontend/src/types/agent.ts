export interface Agent {
  id: string;
  name: string;
  description: string | null;
  model: string;
  status: AgentStatus;
  created_at: string;
  updated_at: string;
  tools: AgentToolAssociation[];
}

export type AgentStatus = 'active' | 'inactive' | 'paused';

export interface AgentToolAssociation {
  tool_id: string;
  tool_name: string;
  is_enabled: boolean;
  added_at: string;
}

export interface AgentCreateRequest {
  name: string;
  description?: string | null;
  model: string;
  status?: AgentStatus;
}

export interface AgentUpdateRequest {
  name?: string;
  description?: string | null;
  model?: string;
  status?: AgentStatus;
}

export interface AgentToolDetail {
  tool_id: string;
  tool_name: string;
  mcp_id: string | null;
  is_enabled: boolean;
  added_at: string;
}

export interface AgentInvokeRequest {
  prompt: string;
}

/* ---- Content blocks inside a conversation message ---- */

export interface ToolUseBlock {
  toolUse: {
    toolUseId: string;
    name: string;
    input: unknown;
  };
}

export interface ToolResultBlock {
  toolResult: {
    toolUseId: string;
    content: { text?: string }[];
    status: 'success' | 'error';
  };
}

export interface TextBlock {
  text: string;
}

export type ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | Record<string, unknown>;

export interface AgentMessage {
  role: 'user' | 'assistant';
  content: ContentBlock[];
}

export interface AgentInvokeResponse {
  agent_id: string;
  response: string;
  messages: AgentMessage[];
}
