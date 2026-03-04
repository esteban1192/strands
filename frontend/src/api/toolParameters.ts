import apiClient from './client';
import type { ToolParameter, ToolParameterCreateRequest, ToolParameterUpdateRequest } from '@/types';

const BASE = '/tool-parameters';

export const toolParameterApi = {
  getByToolId: (toolId: string) =>
    apiClient.get<ToolParameter[]>(`${BASE}/tool/${toolId}`).then((r) => r.data),

  getById: (id: string) =>
    apiClient.get<ToolParameter>(`${BASE}/${id}`).then((r) => r.data),

  create: (data: ToolParameterCreateRequest) =>
    apiClient.post<ToolParameter>(BASE, data).then((r) => r.data),

  update: (id: string, data: ToolParameterUpdateRequest) =>
    apiClient.put<ToolParameter>(`${BASE}/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`${BASE}/${id}`).then((r) => r.data),
};
