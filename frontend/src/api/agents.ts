import apiClient from './client';
import type { Agent, AgentCreateRequest, AgentUpdateRequest, AgentInvokeResponse, AgentToolDetail } from '@/types';

const BASE = '/agents';

export const agentApi = {
  getAll: () =>
    apiClient.get<Agent[]>(BASE).then((r) => r.data),

  getById: (id: string) =>
    apiClient.get<Agent>(`${BASE}/${id}`).then((r) => r.data),

  create: (data: AgentCreateRequest) =>
    apiClient.post<Agent>(BASE, data).then((r) => r.data),

  update: (id: string, data: AgentUpdateRequest) =>
    apiClient.put<Agent>(`${BASE}/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`${BASE}/${id}`).then((r) => r.data),

  addTool: (agentId: string, toolId: string) =>
    apiClient.post(`${BASE}/${agentId}/tools/${toolId}`).then((r) => r.data),

  getTools: (agentId: string) =>
    apiClient.get<AgentToolDetail[]>(`${BASE}/${agentId}/tools`).then((r) => r.data),

  removeTool: (agentId: string, toolId: string) =>
    apiClient.delete(`${BASE}/${agentId}/tools/${toolId}`).then((r) => r.data),

  invoke: (agentId: string, prompt: string) =>
    apiClient.post<AgentInvokeResponse>(`${BASE}/${agentId}/invoke`, { prompt }).then((r) => r.data),
};
