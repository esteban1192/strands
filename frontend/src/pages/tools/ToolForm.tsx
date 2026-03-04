import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toolApi, mcpApi } from '@/api';
import { useApi } from '@/hooks';
import { LoadingSpinner, ErrorMessage } from '@/components/common';
import type { ToolCreateRequest } from '@/types';
import '../shared/FormPage.css';

export default function ToolForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id) && id !== 'new';
  const navigate = useNavigate();

  const { data: mcps } = useApi(() => mcpApi.getAll());

  const [form, setForm] = useState<ToolCreateRequest>({
    name: '',
    description: '',
    mcp_id: null,
    is_active: true,
  });
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isEdit) return;
    toolApi.getById(id!)
      .then((tool) => {
        setForm({
          name: tool.name,
          description: tool.description,
          mcp_id: tool.mcp_id,
          is_active: tool.is_active,
        });
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
        await toolApi.update(id!, payload);
      } else {
        await toolApi.create(payload);
      }
      navigate('/tools');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save tool');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div className="form-page">
      <div className="page-header">
        <h1>{isEdit ? 'Edit Tool' : 'New Tool'}</h1>
      </div>

      {error && <ErrorMessage message={error} />}

      <form className="entity-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="name">Name *</label>
          <input id="name" type="text" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Tool name" />
        </div>

        <div className="form-field">
          <label htmlFor="description">Description</label>
          <textarea id="description" value={form.description ?? ''} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value || null }))} placeholder="Optional description" rows={3} />
        </div>

        <div className="form-field">
          <label htmlFor="mcp_id">MCP</label>
          <select id="mcp_id" value={form.mcp_id ?? ''} onChange={(e) => setForm((f) => ({ ...f, mcp_id: e.target.value || null }))}>
            <option value="">None</option>
            {mcps?.map((mcp) => (
              <option key={mcp.id} value={mcp.id}>{mcp.name}</option>
            ))}
          </select>
        </div>

        <div className="form-field form-field--inline">
          <label>
            <input type="checkbox" checked={form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
            Active
          </label>
        </div>

        <div className="form-actions">
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/tools')}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving...' : isEdit ? 'Update Tool' : 'Create Tool'}</button>
        </div>
      </form>
    </div>
  );
}
