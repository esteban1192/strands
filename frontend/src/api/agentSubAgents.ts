import apiClient from './client';
import type { AgentSubAgent } from '@/types';

const subAgentsUrl = (agentId: string) => `/agents/${agentId}/sub-agents`;

export const agentSubAgentApi = {
  /** List all sub-agents linked to a parent agent. */
  list: (agentId: string) =>
    apiClient.get<AgentSubAgent[]>(subAgentsUrl(agentId)).then((r) => r.data),

  /** Link a child agent as a sub-agent. */
  add: (agentId: string, childAgentId: string) =>
    apiClient
      .post<AgentSubAgent>(`${subAgentsUrl(agentId)}/${childAgentId}`)
      .then((r) => r.data),

  /** Remove a sub-agent link. */
  remove: (agentId: string, childAgentId: string) =>
    apiClient
      .delete(`${subAgentsUrl(agentId)}/${childAgentId}`)
      .then((r) => r.data),
};
