import apiClient from './client';
import type { Chat, ChatDetail, ChatSendMessageResponse } from '@/types';

export const chatApi = {
  /** List all chats for an agent (metadata only, most recent first). */
  listByAgent: (agentId: string) =>
    apiClient.get<Chat[]>(`/agents/${agentId}/chats`).then((r) => r.data),

  /** Get a single chat with all its messages. */
  getById: (agentId: string, chatId: string) =>
    apiClient.get<ChatDetail>(`/agents/${agentId}/chats/${chatId}`).then((r) => r.data),

  /** Create a new chat by sending the first message. */
  create: (agentId: string, prompt: string) =>
    apiClient
      .post<ChatSendMessageResponse>(`/agents/${agentId}/chats`, { prompt })
      .then((r) => r.data),

  /** Send a follow-up message in an existing chat. */
  sendMessage: (agentId: string, chatId: string, prompt: string) =>
    apiClient
      .post<ChatSendMessageResponse>(`/agents/${agentId}/chats/${chatId}/messages`, { prompt })
      .then((r) => r.data),

  /** Delete a chat and all its messages. */
  delete: (agentId: string, chatId: string) =>
    apiClient.delete(`/agents/${agentId}/chats/${chatId}`).then((r) => r.data),

  /** Approve a pending tool call. */
  approveToolCall: (agentId: string, chatId: string, messageId: string) =>
    apiClient
      .post<ChatSendMessageResponse>(
        `/agents/${agentId}/chats/${chatId}/messages/${messageId}/approve`,
      )
      .then((r) => r.data),

  /** Reject a pending tool call. */
  rejectToolCall: (agentId: string, chatId: string, messageId: string) =>
    apiClient
      .post<ChatSendMessageResponse>(
        `/agents/${agentId}/chats/${chatId}/messages/${messageId}/reject`,
      )
      .then((r) => r.data),
};
