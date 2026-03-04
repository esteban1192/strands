import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '@/hooks';
import { mcpApi } from '@/api';
import { LoadingSpinner, ErrorMessage, EmptyState, ConfirmDialog } from '@/components/common';
import type { MCP } from '@/types';
import '../shared/ListPage.css';

export default function MCPList() {
  const { data: mcps, loading, error, refetch } = useApi(() => mcpApi.getAll());
  const [deleting, setDeleting] = useState<MCP | null>(null);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleDelete = async () => {
    if (!deleting) return;
    await mcpApi.delete(deleting.id);
    setDeleting(null);
    refetch();
  };

  const handleSync = async (e: React.MouseEvent, mcp: MCP) => {
    e.stopPropagation();
    setSyncing(mcp.id);
    setSyncMessage(null);
    try {
      const result = await mcpApi.syncTools(mcp.id);
      setSyncMessage(`${mcp.name}: ${result.message}`);
      refetch();
    } catch (err: unknown) {
      setSyncMessage(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(null);
    }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} onRetry={refetch} />;

  return (
    <div className="list-page">
      <div className="page-header">
        <div>
          <h1>MCPs</h1>
          <p className="page-subtitle">Manage Model Context Protocol servers</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/mcps/new')}>
          + New MCP
        </button>
      </div>

      {syncMessage && (
        <div className="sync-message" style={{ padding: '8px 12px', marginBottom: '12px', background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: '6px', fontSize: '14px' }}>
          {syncMessage}
        </div>
      )}

      {mcps && mcps.length > 0 ? (
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Transport</th>
                <th>Tools</th>
                <th>Last Synced</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {mcps.map((mcp) => (
                <tr key={mcp.id} onClick={() => navigate(`/mcps/${mcp.id}`)} className="clickable-row">
                  <td className="cell-primary">{mcp.name}</td>
                  <td>{mcp.transport_type.replace('_', ' ')}</td>
                  <td>{mcp.tools_count}</td>
                  <td className="cell-date">{mcp.synced_at ? new Date(mcp.synced_at).toLocaleString() : '—'}</td>
                  <td className="cell-date">{new Date(mcp.created_at).toLocaleDateString()}</td>
                  <td className="cell-actions">
                    <button
                      className="btn btn-icon"
                      title="Sync Tools"
                      disabled={syncing === mcp.id}
                      onClick={(e) => handleSync(e, mcp)}
                    >
                      {syncing === mcp.id ? '⟳' : '↻'}
                    </button>
                    <button className="btn btn-icon" title="Edit" onClick={(e) => { e.stopPropagation(); navigate(`/mcps/${mcp.id}/edit`); }}>✎</button>
                    <button className="btn btn-icon btn-icon--danger" title="Delete" onClick={(e) => { e.stopPropagation(); setDeleting(mcp); }}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No MCPs yet"
          description="Create your first MCP to get started."
          action={{ label: '+ New MCP', onClick: () => navigate('/mcps/new') }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete MCP"
          message={`Are you sure you want to delete "${deleting.name}"? All associated tools will also be affected.`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
