export type WebhookSourceType = 'AWS_SNS';

export interface Webhook {
  id: string;
  name: string;
  description: string | null;
  agent_id: string;
  agent_name: string | null;
  source_type: WebhookSourceType;
  is_active: boolean;
  prompt: string | null;
  invoke_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface WebhookCreateRequest {
  name: string;
  description?: string | null;
  agent_id: string;
  source_type?: WebhookSourceType;
  is_active?: boolean;
  prompt?: string | null;
}

export interface WebhookUpdateRequest {
  name?: string;
  description?: string | null;
  agent_id?: string;
  source_type?: WebhookSourceType;
  is_active?: boolean;
  prompt?: string | null;
}

export interface WebhookInvocation {
  id: string;
  webhook_id: string;
  chat_id: string | null;
  source_ip: string | null;
  raw_payload: Record<string, unknown> | null;
  status: string;
  error_message: string | null;
  created_at: string;
}
