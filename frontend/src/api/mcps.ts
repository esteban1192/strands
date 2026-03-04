import apiClient from './client';
import type { MCP, MCPCreateRequest, MCPUpdateRequest, MCPSyncToolsResponse } from '@/types';
import type { Tool } from '@/types';

const BASE = '/mcps';

export const mcpApi = {
  getAll: () =>
    apiClient.get<MCP[]>(BASE).then((r) => r.data),

  getById: (id: string) =>
    apiClient.get<MCP>(`${BASE}/${id}`).then((r) => r.data),

  create: (data: MCPCreateRequest) =>
    apiClient.post<MCP>(BASE, data).then((r) => r.data),

  update: (id: string, data: MCPUpdateRequest) =>
    apiClient.put<MCP>(`${BASE}/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`${BASE}/${id}`).then((r) => r.data),

  syncTools: (id: string) =>
    apiClient.post<MCPSyncToolsResponse>(`${BASE}/${id}/sync-tools`).then((r) => r.data),

  getTools: (id: string) =>
    apiClient.get<Tool[]>(`${BASE}/${id}/tools`).then((r) => r.data),
};
