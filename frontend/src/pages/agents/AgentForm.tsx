import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { agentApi } from '@/api';
import { LoadingSpinner, ErrorMessage } from '@/components/common';
import type { AgentCreateRequest, AgentStatus } from '@/types';
import ToolSelector from './ToolSelector';
import '../shared/FormPage.css';

const STATUS_OPTIONS: AgentStatus[] = ['active', 'inactive', 'paused'];

export default function AgentForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id) && id !== 'new';
  const navigate = useNavigate();

  const [form, setForm] = useState<AgentCreateRequest>({
    name: '',
    description: '',
    model: '',
    status: 'active',
  });
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isEdit) return;
    agentApi.getById(id!)
      .then((agent) => {
        setForm({ name: agent.name, description: agent.description, model: agent.model, status: agent.status });
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id, isEdit]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const payload = { ...form };
      if (isEdit) {
        await agentApi.update(id!, payload);
      } else {
        await agentApi.create(payload);
      }
      navigate('/agents');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save agent';
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div className="form-page">
      <div className="page-header">
        <h1>{isEdit ? 'Edit Agent' : 'New Agent'}</h1>
      </div>

      {error && <ErrorMessage message={error} />}

      <form className="entity-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="name">Name *</label>
          <input
            id="name"
            type="text"
            required
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Agent name"
          />
        </div>

        <div className="form-field">
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            value={form.description ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value || null }))}
            placeholder="Optional description"
            rows={3}
          />
        </div>

        <div className="form-field">
          <label htmlFor="model">Model *</label>
          <input
            id="model"
            type="text"
            required
            value={form.model}
            onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
            placeholder="e.g., gpt-4, claude-3-sonnet, etc."
          />
        </div>

        <div className="form-field">
          <label htmlFor="status">Status</label>
          <select
            id="status"
            value={form.status}
            onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as AgentStatus }))}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        {isEdit && id && <ToolSelector agentId={id} />}

        <div className="form-actions">
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/agents')}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving...' : isEdit ? 'Update Agent' : 'Create Agent'}
          </button>
        </div>
      </form>
    </div>
  );
}
