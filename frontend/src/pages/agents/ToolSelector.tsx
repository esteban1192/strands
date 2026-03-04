import { useState, useEffect, useCallback, useMemo } from 'react';
import { agentApi, mcpApi } from '@/api';
import type { MCP, Tool, AgentToolDetail } from '@/types';
import './ToolSelector.css';

const PAGE_SIZE = 8;

interface ToolSelectorProps {
  agentId: string;
}

export default function ToolSelector({ agentId }: ToolSelectorProps) {
  // Data
  const [mcps, setMcps] = useState<MCP[]>([]);
  const [selectedMcpId, setSelectedMcpId] = useState<string>('');
  const [tools, setTools] = useState<Tool[]>([]);
  const [assignedTools, setAssignedTools] = useState<AgentToolDetail[]>([]);

  // UI state
  const [loadingMcps, setLoadingMcps] = useState(true);
  const [loadingTools, setLoadingTools] = useState(false);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // ── Load MCPs + assigned tools on mount ───────────────
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

  // ── Load tools when selected MCP changes ──────────────
  const fetchTools = useCallback(async (mcpId: string) => {
    if (!mcpId) { setTools([]); return; }
    setLoadingTools(true);
    setError(null);
    setPage(1);
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

  // ── Derived data ──────────────────────────────────────
  const assignedIds = useMemo(
    () => new Set(assignedTools.map((t) => t.tool_id)),
    [assignedTools],
  );

  const totalPages = Math.max(1, Math.ceil(tools.length / PAGE_SIZE));
  const paginatedTools = tools.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // ── Toggle tool assignment ────────────────────────────
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
          },
        ]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update tool assignment');
    } finally {
      setToggling(null);
    }
  };

  // ── Render ────────────────────────────────────────────
  if (loadingMcps) {
    return <div className="tool-selector__status">Loading MCPs…</div>;
  }

  return (
    <div className="tool-selector">
      <div className="tool-selector__header">
        <h3>Tools</h3>
        <span className="tool-selector__count">{assignedTools.length} assigned</span>
      </div>

      {/* MCP filter */}
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

      {error && <div className="tool-selector__error">{error}</div>}

      {/* Tool list */}
      <div className="tool-selector__list">
        {loadingTools ? (
          <div className="tool-selector__status">Loading tools…</div>
        ) : paginatedTools.length === 0 ? (
          <div className="tool-selector__empty">
            {selectedMcpId ? 'No tools found for this MCP' : 'Select an MCP to see tools'}
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

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="tool-selector__pagination">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            ← Prev
          </button>
          <span className="tool-selector__page-info">
            {page} / {totalPages}
          </span>
          <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
