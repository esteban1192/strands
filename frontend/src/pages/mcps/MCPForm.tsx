import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { mcpApi } from '@/api';
import { LoadingSpinner, ErrorMessage } from '@/components/common';
import type { MCPCreateRequest, MCPTransportType } from '@/types';
import '../shared/FormPage.css';

export default function MCPForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id) && id !== 'new';
  const navigate = useNavigate();

  const [form, setForm] = useState<MCPCreateRequest>({
    name: '',
    description: '',
    transport_type: 'streamable_http',
    url: '',
    command: '',
    args: [],
    env: [],
  });
  const [argsText, setArgsText] = useState('');
  const [envText, setEnvText] = useState('');
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isEdit) return;
    mcpApi.getById(id!)
      .then((mcp) => {
        setForm({
          name: mcp.name,
          description: mcp.description,
          transport_type: mcp.transport_type,
          url: mcp.url,
          command: mcp.command,
          args: mcp.args,
          env: mcp.env,
        });
        setArgsText(mcp.args ? mcp.args.join('\n') : '');
        setEnvText(mcp.env ? mcp.env.join('\n') : '');
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id, isEdit]);

  const handleTransportChange = (transport: MCPTransportType) => {
    setForm((f) => ({ ...f, transport_type: transport }));
  };

  const handleArgsChange = (text: string) => {
    setArgsText(text);
    const args = text.split('\n').map((s) => s.trim()).filter(Boolean);
    setForm((f) => ({ ...f, args: args.length > 0 ? args : [] }));
  };

  const handleEnvChange = (text: string) => {
    setEnvText(text);
    const keys = text.split('\n').map((s) => s.trim()).filter(Boolean);
    setForm((f) => ({ ...f, env: keys.length > 0 ? keys : [] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form };
      if (isEdit) {
        await mcpApi.update(id!, payload);
      } else {
        await mcpApi.create(payload);
      }
      navigate('/mcps');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save MCP');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner />;

  const isStdio = form.transport_type === 'stdio';

  return (
    <div className="form-page">
      <div className="page-header">
        <h1>{isEdit ? 'Edit MCP' : 'New MCP'}</h1>
      </div>

      {error && <ErrorMessage message={error} />}

      <form className="entity-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="name">Name *</label>
          <input id="name" type="text" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="MCP name" />
        </div>

        <div className="form-field">
          <label htmlFor="description">Description</label>
          <textarea id="description" value={form.description ?? ''} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value || null }))} placeholder="Optional description" rows={3} />
        </div>

        <div className="form-field">
          <label htmlFor="transport_type">Transport Type</label>
          <select
            id="transport_type"
            value={form.transport_type}
            onChange={(e) => handleTransportChange(e.target.value as MCPTransportType)}
          >
            <option value="streamable_http">Streamable HTTP</option>
            <option value="stdio">Stdio</option>
          </select>
        </div>

        {!isStdio && (
          <div className="form-field">
            <label htmlFor="url">URL *</label>
            <input
              id="url"
              type="url"
              required
              value={form.url ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value || null }))}
              placeholder="https://example.com/mcp"
            />
          </div>
        )}

        {isStdio && (
          <>
            <div className="form-field">
              <label htmlFor="command">Command *</label>
              <input
                id="command"
                type="text"
                required
                value={form.command ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, command: e.target.value || null }))}
                placeholder="e.g. npx, python, node"
              />
            </div>

            <div className="form-field">
              <label htmlFor="args">Arguments (one per line)</label>
              <textarea
                id="args"
                value={argsText}
                onChange={(e) => handleArgsChange(e.target.value)}
                placeholder={"e.g.\n-y\n@modelcontextprotocol/server-memory"}
                rows={4}
              />
            </div>

            <div className="form-field">
              <label htmlFor="env">Environment Variable Names (one per line)</label>
              <textarea
                id="env"
                value={envText}
                onChange={(e) => handleEnvChange(e.target.value)}
                placeholder={"e.g.\nAWS_ACCESS_KEY_ID\nAWS_SECRET_ACCESS_KEY\nAWS_DEFAULT_REGION"}
                rows={3}
              />
            </div>
          </>
        )}

        <div className="form-actions">
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/mcps')}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving...' : isEdit ? 'Update MCP' : 'Create MCP'}</button>
        </div>
      </form>
    </div>
  );
}
