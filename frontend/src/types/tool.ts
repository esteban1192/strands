export interface Tool {
  id: string;
  mcp_id: string | null;
  mcp_name: string | null;
  name: string;
  description: string | null;
  is_active: boolean;
  requires_approval: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedToolsResponse {
  items: Tool[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ToolCreateRequest {
  name: string;
  mcp_id?: string | null;
  description?: string | null;
  is_active?: boolean;
  requires_approval?: boolean;
}

export interface ToolUpdateRequest {
  name?: string;
  mcp_id?: string | null;
  description?: string | null;
  is_active?: boolean;
  requires_approval?: boolean;
}
