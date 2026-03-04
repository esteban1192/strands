import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '@/hooks';
import { toolApi, mcpApi } from '@/api';
import { LoadingSpinner, ErrorMessage, EmptyState, StatusBadge, ConfirmDialog } from '@/components/common';
import type { Tool, PaginatedToolsResponse, MCP } from '@/types';
import '../shared/ListPage.css';

const PAGE_SIZE = 20;

export default function ToolList() {
  const [page, setPage] = useState(1);
  const [mcpFilter, setMcpFilter] = useState<string>('');
  const navigate = useNavigate();

  const { data: mcps } = useApi<MCP[]>(() => mcpApi.getAll(), []);
  const { data: paginated, loading, error, refetch } = useApi<PaginatedToolsResponse>(
    () => toolApi.getAll({ page, page_size: PAGE_SIZE, mcp_id: mcpFilter || undefined }),
    [page, mcpFilter],
  );
  const [deleting, setDeleting] = useState<Tool | null>(null);

  const handleDelete = async () => {
    if (!deleting) return;
    await toolApi.delete(deleting.id);
    setDeleting(null);
    refetch();
  };

  const handleMcpFilterChange = (value: string) => {
    setMcpFilter(value);
    setPage(1);
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} onRetry={refetch} />;

  const tools = paginated?.items ?? [];
  const totalPages = paginated?.total_pages ?? 1;
  const total = paginated?.total ?? 0;

  return (
    <div className="list-page">
      <div className="page-header">
        <div>
          <h1>Tools</h1>
          <p className="page-subtitle">Manage available tools</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/tools/new')}>
          + New Tool
        </button>
      </div>

      <div className="list-filters">
        <select
          className="filter-select"
          value={mcpFilter}
          onChange={(e) => handleMcpFilterChange(e.target.value)}
        >
          <option value="">All MCPs</option>
          {mcps?.map((mcp) => (
            <option key={mcp.id} value={mcp.id}>{mcp.name}</option>
          ))}
        </select>
        <span className="filter-count">{total} tool{total !== 1 ? 's' : ''}</span>
      </div>

      {tools.length > 0 ? (
        <>
          <div className="data-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>MCP</th>
                  <th>Active</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tools.map((tool) => (
                  <tr key={tool.id} onClick={() => navigate(`/tools/${tool.id}`)} className="clickable-row">
                    <td className="cell-primary">{tool.name}</td>
                    <td className="cell-mcp">{tool.mcp_name ?? '—'}</td>
                    <td><StatusBadge status={tool.is_active ? 'Active' : 'Inactive'} /></td>
                    <td className="cell-date">{new Date(tool.created_at).toLocaleDateString()}</td>
                    <td className="cell-actions">
                      <button className="btn btn-icon" title="Edit" onClick={(e) => { e.stopPropagation(); navigate(`/tools/${tool.id}/edit`); }}>✎</button>
                      <button className="btn btn-icon btn-icon--danger" title="Delete" onClick={(e) => { e.stopPropagation(); setDeleting(tool); }}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn btn-secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                ← Previous
              </button>
              <span className="pagination-info">
                Page {page} of {totalPages}
              </span>
              <button
                className="btn btn-secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next →
              </button>
            </div>
          )}
        </>
      ) : (
        <EmptyState
          title="No tools yet"
          description={mcpFilter ? 'No tools found for this MCP.' : 'Create your first tool to get started.'}
          action={!mcpFilter ? { label: '+ New Tool', onClick: () => navigate('/tools/new') } : undefined}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete Tool"
          message={`Are you sure you want to delete "${deleting.name}"?`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
