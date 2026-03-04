import { useApi } from '@/hooks';
import { agentApi, toolApi, mcpApi } from '@/api';
import { LoadingSpinner, ErrorMessage } from '@/components/common';
import { useNavigate } from 'react-router-dom';
import './Dashboard.css';

export default function Dashboard() {
  const agents = useApi(() => agentApi.getAll());
  const tools = useApi(() => toolApi.getAll());
  const mcps = useApi(() => mcpApi.getAll());

  const navigate = useNavigate();

  const isLoading = agents.loading || tools.loading || mcps.loading;
  const error = agents.error || tools.error || mcps.error;

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} onRetry={() => { agents.refetch(); tools.refetch(); mcps.refetch(); }} />;

  const stats = [
    { label: 'Agents', count: agents.data?.length ?? 0, path: '/agents', icon: '⬡' },
    { label: 'Tools', count: tools.data?.total ?? 0, path: '/tools', icon: '⚙' },
    { label: 'MCPs', count: mcps.data?.length ?? 0, path: '/mcps', icon: '⬢' },
  ];

  return (
    <div className="dashboard">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p className="page-subtitle">Overview of your Strands workspace</p>
      </div>

      <div className="stats-grid">
        {stats.map(({ label, count, path, icon }) => (
          <button key={label} className="stat-card" onClick={() => navigate(path)}>
            <span className="stat-icon">{icon}</span>
            <div className="stat-info">
              <span className="stat-count">{count}</span>
              <span className="stat-label">{label}</span>
            </div>
          </button>
        ))}
      </div>

      <section className="dashboard-section">
        <h2>Recent Agents</h2>
        {agents.data && agents.data.length > 0 ? (
          <div className="card-list">
            {agents.data.slice(0, 5).map((agent) => (
              <div key={agent.id} className="mini-card" onClick={() => navigate(`/agents/${agent.id}`)}>
                <strong>{agent.name}</strong>
                <span className={`status-dot status-dot--${agent.status}`} />
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted">No agents yet.</p>
        )}
      </section>
    </div>
  );
}
