import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '@/hooks';
import { toolApi, mcpApi } from '@/api';
import { LoadingSpinner, ErrorMessage, EmptyState, StatusBadge, ConfirmDialog } from '@/components/common';
import type { Tool, PaginatedToolsResponse, MCP } from '@/types';
import '../shared/ListPage.css';

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export default function ToolList() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [mcpFilter, setMcpFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState<Tool | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const navigate = useNavigate();
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(value);
      setPage(1);
    }, 300);
  }, []);

  useEffect(() => () => clearTimeout(debounceRef.current), []);

  const { data: mcps } = useApi<MCP[]>(() => mcpApi.getAll(), []);
  const { data: paginated, loading, error, refetch } = useApi<PaginatedToolsResponse>(
    () => toolApi.getAll({
      page,
      page_size: pageSize,
      mcp_id: mcpFilter || undefined,
      search: debouncedSearch || undefined,
    }),
    [page, pageSize, mcpFilter, debouncedSearch],
  );

  const initialLoad = loading && !paginated;

  const tools = paginated?.items ?? [];
  const totalPages = paginated?.total_pages ?? 1;
  const total = paginated?.total ?? 0;

  const allOnPageSelected = tools.length > 0 && tools.every((t) => selected.has(t.id));

  const handleSelectAll = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) {
        tools.forEach((t) => next.delete(t.id));
      } else {
        tools.forEach((t) => next.add(t.id));
      }
      return next;
    });
  };

  const handleSelectOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDelete = async () => {
    if (!deleting) return;
    await toolApi.delete(deleting.id);
    setDeleting(null);
    setSelected((prev) => { const n = new Set(prev); n.delete(deleting.id); return n; });
    refetch();
  };

  const handleBulkDelete = async () => {
    if (selected.size === 0) return;
    await toolApi.bulkDelete([...selected]);
    setSelected(new Set());
    setBulkDeleting(false);
    refetch();
  };

  const handleMcpFilterChange = (value: string) => {
    setMcpFilter(value);
    setPage(1);
  };

  const handlePageSizeChange = (value: number) => {
    setPageSize(value);
    setPage(1);
  };

  if (initialLoad) return <LoadingSpinner />;
  if (error && !paginated) return <ErrorMessage message={error} onRetry={refetch} />;

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
        <input
          type="text"
          className="filter-search"
          placeholder="Search tools..."
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
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
        <div className="filter-page-size">
          <label htmlFor="page-size">Per page</label>
          <select
            id="page-size"
            className="filter-select filter-select--small"
            value={pageSize}
            onChange={(e) => handlePageSizeChange(Number(e.target.value))}
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
        <span className="filter-count">{total} tool{total !== 1 ? 's' : ''}</span>
      </div>

      {error && <ErrorMessage message={error} onRetry={refetch} />}

      {selected.size > 0 && (
        <div className="bulk-actions">
          <span className="bulk-actions__count">{selected.size} selected</span>
          <button className="btn btn-danger btn-sm" onClick={() => setBulkDeleting(true)}>
            Delete selected
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setSelected(new Set())}>
            Clear selection
          </button>
        </div>
      )}

      {tools.length > 0 || loading ? (
        <>
          <div className={`data-table-wrapper${loading ? ' data-table-wrapper--loading' : ''}`}>
            {loading && <div className="table-loading-overlay"><LoadingSpinner /></div>}
            <table className="data-table">
              <thead>
                <tr>
                  <th className="cell-checkbox">
                    <input
                      type="checkbox"
                      checked={allOnPageSelected}
                      onChange={handleSelectAll}
                      title="Select all on this page"
                    />
                  </th>
                  <th>Name</th>
                  <th>MCP</th>
                  <th>Active</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tools.map((tool) => (
                  <tr
                    key={tool.id}
                    className={`clickable-row${selected.has(tool.id) ? ' row-selected' : ''}`}
                    onClick={() => navigate(`/tools/${tool.id}`)}
                  >
                    <td className="cell-checkbox" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(tool.id)}
                        onChange={() => handleSelectOne(tool.id)}
                      />
                    </td>
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
          title="No tools found"
          description={
            debouncedSearch
              ? 'No tools match your search.'
              : mcpFilter
                ? 'No tools found for this MCP.'
                : 'Create your first tool to get started.'
          }
          action={!mcpFilter && !debouncedSearch ? { label: '+ New Tool', onClick: () => navigate('/tools/new') } : undefined}
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

      {bulkDeleting && (
        <ConfirmDialog
          title="Delete Selected Tools"
          message={`Are you sure you want to delete ${selected.size} tool${selected.size !== 1 ? 's' : ''}? This cannot be undone.`}
          confirmLabel="Delete All"
          variant="danger"
          onConfirm={handleBulkDelete}
          onCancel={() => setBulkDeleting(false)}
        />
      )}
    </div>
  );
}
