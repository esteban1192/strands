export interface AgentSubAgent {
  id: string;
  parent_agent_id: string;
  child_agent_id: string;
  child_agent_name: string;
  child_agent_description: string | null;
  child_agent_status: string;
  is_enabled: boolean;
  added_at: string;
}
