import { useState, useEffect, useMemo } from 'react';
import { agentApi, agentSubAgentApi } from '@/api';
import type { Agent, AgentSubAgent } from '@/types';
import './SubAgentSelector.css';

interface SubAgentSelectorProps {
  agentId: string;
}

export default function SubAgentSelector({ agentId }: SubAgentSelectorProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [subAgents, setSubAgents] = useState<AgentSubAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const [allAgents, linked] = await Promise.all([
          agentApi.getAll(),
          agentSubAgentApi.list(agentId),
        ]);
        if (cancelled) return;
        // Exclude the current agent from the list of candidates
        setAgents(allAgents.filter((a) => a.id !== agentId));
        setSubAgents(linked);
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    init();
    return () => { cancelled = true; };
  }, [agentId]);

  const linkedIds = useMemo(
    () => new Set(subAgents.map((s) => s.child_agent_id)),
    [subAgents],
  );

  const handleToggle = async (agent: Agent) => {
    if (toggling) return;
    setToggling(agent.id);
    setError(null);

    const isLinked = linkedIds.has(agent.id);

    try {
      if (isLinked) {
        await agentSubAgentApi.remove(agentId, agent.id);
        setSubAgents((prev) => prev.filter((s) => s.child_agent_id !== agent.id));
      } else {
        const created = await agentSubAgentApi.add(agentId, agent.id);
        setSubAgents((prev) => [...prev, created]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update sub-agent assignment');
    } finally {
      setToggling(null);
    }
  };

  if (loading) {
    return <div className="sub-agent-selector__status">Loading agents…</div>;
  }

  return (
    <div className="sub-agent-selector">
      <div className="sub-agent-selector__header">
        <h3>Sub-Agents</h3>
        <span className="sub-agent-selector__count">{subAgents.length} linked</span>
      </div>

      <p className="sub-agent-selector__hint">
        Link other agents as sub-agents. The parent agent can delegate tasks to them.
        Sub-agent invocations always require user approval.
      </p>

      {error && <div className="sub-agent-selector__error">{error}</div>}

      <div className="sub-agent-selector__list">
        {agents.length === 0 ? (
          <div className="sub-agent-selector__empty">No other agents available</div>
        ) : (
          agents.map((agent) => {
            const isLinked = linkedIds.has(agent.id);
            const isToggling = toggling === agent.id;

            return (
              <div
                key={agent.id}
                className={`sub-agent-selector__item${isLinked ? ' sub-agent-selector__item--linked' : ''}`}
                onClick={() => handleToggle(agent)}
              >
                <input
                  type="checkbox"
                  className="sub-agent-selector__checkbox"
                  checked={isLinked}
                  readOnly
                  tabIndex={-1}
                />
                <div className="sub-agent-selector__info">
                  <div className="sub-agent-selector__name">
                    {agent.name}
                    <span className={`sub-agent-selector__status-badge sub-agent-selector__status-badge--${agent.status}`}>
                      {agent.status}
                    </span>
                  </div>
                  {agent.description && (
                    <div className="sub-agent-selector__desc">{agent.description}</div>
                  )}
                  <div className="sub-agent-selector__model">Model: {agent.model}</div>
                </div>
                {!isToggling ? (
                  <span
                    className={`sub-agent-selector__toggle-badge ${
                      isLinked
                        ? 'sub-agent-selector__toggle-badge--remove'
                        : 'sub-agent-selector__toggle-badge--add'
                    }`}
                  >
                    {isLinked ? 'remove' : 'add'}
                  </span>
                ) : (
                  <span className="sub-agent-selector__toggle-badge sub-agent-selector__toggle-badge--add">
                    …
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
