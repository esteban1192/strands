import apiClient from './client';
import type { Tool, ToolCreateRequest, ToolUpdateRequest, PaginatedToolsResponse } from '@/types';

const BASE = '/tools';

export const toolApi = {
  getAll: (params?: { page?: number; page_size?: number; mcp_id?: string }) =>
    apiClient.get<PaginatedToolsResponse>(BASE, { params }).then((r) => r.data),

  getById: (id: string) =>
    apiClient.get<Tool>(`${BASE}/${id}`).then((r) => r.data),

  create: (data: ToolCreateRequest) =>
    apiClient.post<Tool>(BASE, data).then((r) => r.data),

  update: (id: string, data: ToolUpdateRequest) =>
    apiClient.put<Tool>(`${BASE}/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`${BASE}/${id}`).then((r) => r.data),
};
