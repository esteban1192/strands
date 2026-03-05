import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '@/hooks';
import { agentApi } from '@/api';
import { LoadingSpinner, ErrorMessage, EmptyState, StatusBadge, ConfirmDialog } from '@/components/common';
import type { Agent } from '@/types';
import '../shared/ListPage.css';

export default function AgentList() {
  const { data: agents, loading, error, refetch } = useApi(() => agentApi.getAll());
  const [deleting, setDeleting] = useState<Agent | null>(null);
  const navigate = useNavigate();

  const handleDelete = async () => {
    if (!deleting) return;
    await agentApi.delete(deleting.id);
    setDeleting(null);
    refetch();
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} onRetry={refetch} />;

  return (
    <div className="list-page">
      <div className="page-header">
        <div>
          <h1>Agents</h1>
          <p className="page-subtitle">Manage your AI agents</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/agents/new')}>
          + New Agent
        </button>
      </div>

      {agents && agents.length > 0 ? (
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Model</th>
                <th>Status</th>
                <th>Tools</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id} onClick={() => navigate(`/agents/${agent.id}/chat`)} className="clickable-row">
                  <td className="cell-primary">{agent.name}</td>
                  <td className="cell-secondary">{agent.model}</td>
                  <td><StatusBadge status={agent.status} /></td>
                  <td>{agent.tools_count}</td>
                  <td className="cell-date">{new Date(agent.created_at).toLocaleDateString()}</td>
                  <td className="cell-actions">
                    <button
                      className="btn btn-icon"
                      title="Chat"
                      onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}/chat`); }}
                    >
                      💬
                    </button>
                    <button
                      className="btn btn-icon"
                      title="Edit"
                      onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}/edit`); }}
                    >
                      ✎
                    </button>
                    <button
                      className="btn btn-icon btn-icon--danger"
                      title="Delete"
                      onClick={(e) => { e.stopPropagation(); setDeleting(agent); }}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No agents yet"
          description="Create your first agent to get started."
          action={{ label: '+ New Agent', onClick: () => navigate('/agents/new') }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete Agent"
          message={`Are you sure you want to delete "${deleting.name}"? This action cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
