import { createBrowserRouter } from 'react-router-dom';
import { Layout } from '@/components/layout';
import {
  Dashboard,
  AgentList,
  AgentForm,
  AgentChat,
  ToolList,
  ToolForm,
  MCPList,
  MCPForm,
  WebhookList,
  WebhookForm,
} from '@/pages';

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },

      { path: 'agents', element: <AgentList /> },
      { path: 'agents/new', element: <AgentForm /> },
      { path: 'agents/:id', element: <AgentForm /> },
      { path: 'agents/:id/edit', element: <AgentForm /> },
      { path: 'agents/:id/chat', element: <AgentChat /> },

      { path: 'tools', element: <ToolList /> },
      { path: 'tools/new', element: <ToolForm /> },
      { path: 'tools/:id', element: <ToolForm /> },
      { path: 'tools/:id/edit', element: <ToolForm /> },

      { path: 'mcps', element: <MCPList /> },
      { path: 'mcps/new', element: <MCPForm /> },
      { path: 'mcps/:id', element: <MCPForm /> },
      { path: 'mcps/:id/edit', element: <MCPForm /> },

      { path: 'webhooks', element: <WebhookList /> },
      { path: 'webhooks/new', element: <WebhookForm /> },
      { path: 'webhooks/:id', element: <WebhookForm /> },
      { path: 'webhooks/:id/edit', element: <WebhookForm /> },
    ],
  },
]);

export default router;
