import apiClient from './client';
import type { Webhook, WebhookCreateRequest, WebhookUpdateRequest, WebhookInvocation } from '@/types';

const BASE = '/webhooks';

export const webhookApi = {
  getAll: () =>
    apiClient.get<Webhook[]>(BASE).then((r) => r.data),

  getById: (id: string) =>
    apiClient.get<Webhook>(`${BASE}/${id}`).then((r) => r.data),

  create: (data: WebhookCreateRequest) =>
    apiClient.post<Webhook>(BASE, data).then((r) => r.data),

  update: (id: string, data: WebhookUpdateRequest) =>
    apiClient.put<Webhook>(`${BASE}/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`${BASE}/${id}`).then((r) => r.data),

  getInvocations: (id: string, limit = 50, offset = 0) =>
    apiClient
      .get<WebhookInvocation[]>(`${BASE}/${id}/invocations`, { params: { limit, offset } })
      .then((r) => r.data),
};
