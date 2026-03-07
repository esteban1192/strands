import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { agentApi, mcpApi } from '@/api';
import type { MCP, Tool, AgentToolDetail } from '@/types';
import './ToolSelector.css';

const PAGE_SIZE = 8;

interface ToolSelectorProps {
  agentId: string;
}

export default function ToolSelector({ agentId }: ToolSelectorProps) {
  const [mcps, setMcps] = useState<MCP[]>([]);
  const [selectedMcpId, setSelectedMcpId] = useState<string>('');
  const [tools, setTools] = useState<Tool[]>([]);
  const [assignedTools, setAssignedTools] = useState<AgentToolDetail[]>([]);

  const [loadingMcps, setLoadingMcps] = useState(true);
  const [loadingTools, setLoadingTools] = useState(false);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [addToolsOpen, setAddToolsOpen] = useState(false);
  const [selectingAll, setSelectingAll] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const [mcpList, agentTools] = await Promise.all([
          mcpApi.getAll(),
          agentApi.getTools(agentId),
        ]);
        if (cancelled) return;
        setMcps(mcpList);
        setAssignedTools(agentTools);
        if (mcpList.length > 0) {
          setSelectedMcpId(mcpList[0].id);
        }
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        if (!cancelled) setLoadingMcps(false);
      }
    }

    init();
    return () => { cancelled = true; };
  }, [agentId]);

  const fetchTools = useCallback(async (mcpId: string) => {
    if (!mcpId) { setTools([]); return; }
    setLoadingTools(true);
    setError(null);
    setPage(1);
    setSearchQuery('');
    try {
      const list = await mcpApi.getTools(mcpId);
      setTools(list);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load tools');
      setTools([]);
    } finally {
      setLoadingTools(false);
    }
  }, []);

  useEffect(() => {
    if (selectedMcpId) fetchTools(selectedMcpId);
  }, [selectedMcpId, fetchTools]);

  const assignedIds = useMemo(
    () => new Set(assignedTools.map((t) => t.tool_id)),
    [assignedTools],
  );

  const filteredTools = useMemo(() => {
    if (!searchQuery.trim()) return tools;
    const q = searchQuery.toLowerCase();
    return tools.filter(
      (t) => t.name.toLowerCase().includes(q) || t.description?.toLowerCase().includes(q),
    );
  }, [tools, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredTools.length / PAGE_SIZE));
  const paginatedTools = filteredTools.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleToggle = async (tool: Tool) => {
    if (toggling) return;
    setToggling(tool.id);
    setError(null);

    const isAssigned = assignedIds.has(tool.id);

    try {
      if (isAssigned) {
        await agentApi.removeTool(agentId, tool.id);
        setAssignedTools((prev) => prev.filter((t) => t.tool_id !== tool.id));
      } else {
        await agentApi.addTool(agentId, tool.id);
        setAssignedTools((prev) => [
          ...prev,
          {
            tool_id: tool.id,
            tool_name: tool.name,
            mcp_id: tool.mcp_id,
            is_enabled: true,
            added_at: new Date().toISOString(),
            requires_approval: tool.requires_approval,
          },
        ]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update tool assignment');
    } finally {
      setToggling(null);
    }
  };

  const unassignedFiltered = useMemo(
    () => filteredTools.filter((t) => !assignedIds.has(t.id)),
    [filteredTools, assignedIds],
  );

  const handleSelectAll = async () => {
    if (selectingAll || unassignedFiltered.length === 0) return;
    setSelectingAll(true);
    setError(null);

    try {
      const results = await Promise.allSettled(
        unassignedFiltered.map((tool) => agentApi.addTool(agentId, tool.id)),
      );

      const added: AgentToolDetail[] = [];
      results.forEach((result, i) => {
        if (result.status === 'fulfilled') {
          const tool = unassignedFiltered[i];
          added.push({
            tool_id: tool.id,
            tool_name: tool.name,
            mcp_id: tool.mcp_id,
            is_enabled: true,
            added_at: new Date().toISOString(),
            requires_approval: tool.requires_approval,
          });
        }
      });

      if (added.length > 0) {
        setAssignedTools((prev) => [...prev, ...added]);
      }

      const failCount = results.filter((r) => r.status === 'rejected').length;
      if (failCount > 0) {
        setError(`Failed to add ${failCount} of ${unassignedFiltered.length} tools`);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add tools');
    } finally {
      setSelectingAll(false);
    }
  };

  const handleRemoveAssigned = async (toolId: string) => {
    if (toggling) return;
    setToggling(toolId);
    setError(null);
    try {
      await agentApi.removeTool(agentId, toolId);
      setAssignedTools((prev) => prev.filter((t) => t.tool_id !== toolId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to remove tool');
    } finally {
      setToggling(null);
    }
  };

  if (loadingMcps) {
    return <div className="tool-selector__status">Loading tools…</div>;
  }

  return (
    <div className="tool-selector">
      {/* ── Attached tools ── */}
      <div className="tool-selector__header">
        <h3>Attached tools</h3>
        <span className="tool-selector__count">{assignedTools.length}</span>
      </div>

      {assignedTools.length === 0 ? (
        <div className="tool-selector__list">
          <div className="tool-selector__empty">No tools attached yet</div>
        </div>
      ) : (
        <table className="tool-selector__table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Approval</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {assignedTools.map((at) => (
              <tr key={at.tool_id}>
                <td>
                  <Link
                    to={`/tools/${at.tool_id}/edit`}
                    className="tool-selector__link"
                  >
                    {at.tool_name}
                  </Link>
                </td>
                <td>
                  <span className={`tool-selector__approval-badge ${at.requires_approval ? 'tool-selector__approval-badge--yes' : 'tool-selector__approval-badge--no'}`}>
                    {at.requires_approval ? 'required' : 'auto'}
                  </span>
                </td>
                <td>
                  <button
                    type="button"
                    className="tool-selector__toggle-badge tool-selector__toggle-badge--remove"
                    disabled={toggling === at.tool_id}
                    onClick={() => handleRemoveAssigned(at.tool_id)}
                  >
                    {toggling === at.tool_id ? '…' : 'remove'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* ── Add tools (collapsible) ── */}
      <button
        type="button"
        className={`tool-selector__add-trigger${addToolsOpen ? ' tool-selector__add-trigger--open' : ''}`}
        onClick={() => setAddToolsOpen((v) => !v)}
      >
        <span className="tool-selector__add-trigger-icon">{addToolsOpen ? '−' : '+'}</span>
        Add tools
      </button>

      {addToolsOpen && (
        <div className="tool-selector__add-panel">
          <div className="tool-selector__filter">
            <label htmlFor="mcp-filter">Filter by MCP</label>
            <select
              id="mcp-filter"
              value={selectedMcpId}
              onChange={(e) => setSelectedMcpId(e.target.value)}
            >
              {mcps.length === 0 && <option value="">No MCPs available</option>}
              {mcps.map((mcp) => (
                <option key={mcp.id} value={mcp.id}>
                  {mcp.name} ({mcp.tools_count} tools)
                </option>
              ))}
            </select>
          </div>

          <div className="tool-selector__search">
            <input
              type="text"
              placeholder="Search tools…"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
            />
            {searchQuery && (
              <button
                type="button"
                className="tool-selector__search-clear"
                onClick={() => { setSearchQuery(''); setPage(1); }}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>

          {error && <div className="tool-selector__error">{error}</div>}

          {!loadingTools && filteredTools.length > 0 && (
            <div className="tool-selector__bulk-actions">
              <button
                type="button"
                className="tool-selector__select-all"
                disabled={selectingAll || unassignedFiltered.length === 0}
                onClick={handleSelectAll}
              >
                {selectingAll
                  ? `Adding ${unassignedFiltered.length} tools…`
                  : unassignedFiltered.length === 0
                    ? 'All selected'
                    : `Select all (${unassignedFiltered.length})`}
              </button>
            </div>
          )}

          <div className="tool-selector__list">
            {loadingTools ? (
              <div className="tool-selector__status">Loading tools…</div>
            ) : paginatedTools.length === 0 ? (
              <div className="tool-selector__empty">
                {searchQuery
                  ? 'No tools match your search'
                  : selectedMcpId
                    ? 'No tools found for this MCP'
                    : 'Select an MCP to see tools'}
              </div>
            ) : (
              paginatedTools.map((tool) => {
                const isAssigned = assignedIds.has(tool.id);
                const isToggling = toggling === tool.id;

                return (
                  <div
                    key={tool.id}
                    className={`tool-selector__item${isAssigned ? ' tool-selector__item--assigned' : ''}`}
                    onClick={() => handleToggle(tool)}
                  >
                    <input
                      type="checkbox"
                      className="tool-selector__checkbox"
                      checked={isAssigned}
                      readOnly
                      tabIndex={-1}
                    />
                    <div className="tool-selector__info">
                      <div className="tool-selector__name">{tool.name}</div>
                      {tool.description && (
                        <div className="tool-selector__desc">{tool.description}</div>
                      )}
                    </div>
                    {!isToggling ? (
                      <span
                        className={`tool-selector__toggle-badge ${
                          isAssigned
                            ? 'tool-selector__toggle-badge--remove'
                            : 'tool-selector__toggle-badge--add'
                        }`}
                      >
                        {isAssigned ? 'remove' : 'add'}
                      </span>
                    ) : (
                      <span className="tool-selector__toggle-badge tool-selector__toggle-badge--add">
                        …
                      </span>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {totalPages > 1 && (
            <div className="tool-selector__pagination">
              <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                ← Prev
              </button>
              <span className="tool-selector__page-info">
                {page} / {totalPages}
              </span>
              <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                Next →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
