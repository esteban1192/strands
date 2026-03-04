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

export interface AgentInvokeResponse {
  agent_id: string;
  response: string;
}
