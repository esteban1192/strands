import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '@/hooks';
import { webhookApi } from '@/api';
import { LoadingSpinner, ErrorMessage, EmptyState, ConfirmDialog, StatusBadge } from '@/components/common';
import type { Webhook } from '@/types';
import '../shared/ListPage.css';

export default function WebhookList() {
  const { data: webhooks, loading, error, refetch } = useApi(() => webhookApi.getAll());
  const [deleting, setDeleting] = useState<Webhook | null>(null);
  const navigate = useNavigate();

  const handleDelete = async () => {
    if (!deleting) return;
    await webhookApi.delete(deleting.id);
    setDeleting(null);
    refetch();
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} onRetry={refetch} />;

  return (
    <div className="list-page">
      <div className="page-header">
        <div>
          <h1>Webhooks</h1>
          <p className="page-subtitle">Inbound notification endpoints for automated incident analysis</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/webhooks/new')}>
          + New Webhook
        </button>
      </div>

      {webhooks && webhooks.length > 0 ? (
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Agent</th>
                <th>Source</th>
                <th>Status</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {webhooks.map((wh) => (
                <tr key={wh.id} onClick={() => navigate(`/webhooks/${wh.id}`)} className="clickable-row">
                  <td className="cell-primary">{wh.name}</td>
                  <td>{wh.agent_name ?? '—'}</td>
                  <td>{wh.source_type.replace('_', ' ')}</td>
                  <td><StatusBadge status={wh.is_active ? 'active' : 'inactive'} /></td>
                  <td className="cell-date">{new Date(wh.created_at).toLocaleDateString()}</td>
                  <td className="cell-actions">
                    <button
                      className="btn btn-icon"
                      title="Edit"
                      onClick={(e) => { e.stopPropagation(); navigate(`/webhooks/${wh.id}/edit`); }}
                    >✎</button>
                    <button
                      className="btn btn-icon btn-icon--danger"
                      title="Delete"
                      onClick={(e) => { e.stopPropagation(); setDeleting(wh); }}
                    >✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No webhooks yet"
          description="Create a webhook to start receiving automated notifications from AWS SNS."
          action={{ label: '+ New Webhook', onClick: () => navigate('/webhooks/new') }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete Webhook"
          message={`Are you sure you want to delete "${deleting.name}"? This will stop processing notifications sent to this endpoint.`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
