export type MCPTransportType = 'streamable_http' | 'stdio';

export interface MCP {
  id: string;
  name: string;
  description: string | null;
  transport_type: MCPTransportType;
  url: string | null;
  command: string | null;
  args: string[] | null;
  env: string[] | null;
  tools_count: number;
  synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MCPCreateRequest {
  name: string;
  description?: string | null;
  transport_type?: MCPTransportType;
  url?: string | null;
  command?: string | null;
  args?: string[] | null;
  env?: string[] | null;
}

export interface MCPUpdateRequest {
  name?: string;
  description?: string | null;
  transport_type?: MCPTransportType;
  url?: string | null;
  command?: string | null;
  args?: string[] | null;
  env?: string[] | null;
}

export interface MCPSyncToolsResponse {
  mcp_id: string;
  tools_synced: number;
  message: string;
}
