export interface ToolParameter {
  id: string;
  tool_id: string;
  name: string;
  parameter_type: string;
  default_value: string | null;
  is_required: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ToolParameterCreateRequest {
  tool_id: string;
  name: string;
  parameter_type: string;
  default_value?: string | null;
  is_required?: boolean;
  description?: string | null;
}

export interface ToolParameterUpdateRequest {
  name?: string;
  parameter_type?: string;
  default_value?: string | null;
  is_required?: boolean;
  description?: string | null;
}
