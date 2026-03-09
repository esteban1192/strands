import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { webhookApi } from '@/api';
import { agentApi } from '@/api';
import { LoadingSpinner, ErrorMessage } from '@/components/common';
import type { WebhookCreateRequest, WebhookSourceType, Agent } from '@/types';
import type { WebhookInvocation } from '@/types';
import '../shared/FormPage.css';

export default function WebhookForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id) && id !== 'new';
  const navigate = useNavigate();

  const [form, setForm] = useState<WebhookCreateRequest>({
    name: '',
    description: '',
    agent_id: '',
    source_type: 'AWS_SNS',
    is_active: true,
    prompt: '',
  });
  const [invokeUrl, setInvokeUrl] = useState<string | null>(null);
  const [invocations, setInvocations] = useState<WebhookInvocation[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const init = async () => {
      try {
        const agentList = await agentApi.getAll();
        setAgents(agentList);

        if (isEdit) {
          const webhook = await webhookApi.getById(id!);
          setForm({
            name: webhook.name,
            description: webhook.description,
            agent_id: webhook.agent_id,
            source_type: webhook.source_type,
            is_active: webhook.is_active,
            prompt: webhook.prompt ?? '',
          });
          setInvokeUrl(webhook.invoke_url);

          const invs = await webhookApi.getInvocations(id!);
          setInvocations(invs);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    };
    init();
  }, [id, isEdit]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.agent_id) {
      setError('Please select an agent');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (isEdit) {
        await webhookApi.update(id!, form);
      } else {
        await webhookApi.create(form);
      }
      navigate('/webhooks');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save webhook');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyUrl = () => {
    if (!invokeUrl) return;
    navigator.clipboard.writeText(invokeUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div className="form-page">
      <div className="page-header">
        <h1>{isEdit ? 'Edit Webhook' : 'New Webhook'}</h1>
      </div>

      {error && <ErrorMessage message={error} />}

      {isEdit && invokeUrl && (
        <div
          style={{
            padding: '12px 16px',
            marginBottom: '20px',
            background: '#f0f9ff',
            border: '1px solid #bae6fd',
            borderRadius: '8px',
            fontSize: '14px',
          }}
        >
          <strong>Invoke URL</strong>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
            <code style={{ flex: 1, padding: '6px 10px', background: '#fff', borderRadius: '4px', border: '1px solid #e2e8f0', fontSize: '13px', wordBreak: 'break-all' }}>
              {invokeUrl}
            </code>
            <button className="btn btn-secondary" onClick={handleCopyUrl} style={{ whiteSpace: 'nowrap' }}>
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <p style={{ margin: '6px 0 0', color: '#64748b', fontSize: '12px' }}>
            Configure your AWS SNS topic to send notifications to this URL.
          </p>
        </div>
      )}

      <form className="entity-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="name">Name *</label>
          <input
            id="name"
            type="text"
            required
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="e.g. Prod API Alarms"
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
          <label htmlFor="agent_id">Agent *</label>
          <select
            id="agent_id"
            required
            value={form.agent_id}
            onChange={(e) => setForm((f) => ({ ...f, agent_id: e.target.value }))}
          >
            <option value="">Select an agent...</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name} {agent.status !== 'active' ? `(${agent.status})` : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label htmlFor="source_type">Source Type</label>
          <select
            id="source_type"
            value={form.source_type}
            onChange={(e) => setForm((f) => ({ ...f, source_type: e.target.value as WebhookSourceType }))}
          >
            <option value="AWS_SNS">AWS SNS</option>
          </select>
        </div>

        <div className="form-field">
          <label htmlFor="prompt">Custom Instructions</label>
          <textarea
            id="prompt"
            value={form.prompt ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value || null }))}
            placeholder="Optional — provide custom instructions for the agent when this webhook is triggered. Leave empty to use the default investigation prompt."
            rows={8}
          />
        </div>

        <div className="form-field form-field--inline">
          <label>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            {' '}Active
          </label>
        </div>

        <div className="form-actions">
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/webhooks')}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving...' : isEdit ? 'Update Webhook' : 'Create Webhook'}
          </button>
        </div>
      </form>

      {isEdit && invocations.length > 0 && (
        <div style={{ marginTop: '32px' }}>
          <h2 style={{ fontSize: '18px', marginBottom: '12px' }}>Recent Invocations</h2>
          <div className="data-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Status</th>
                  <th>Source IP</th>
                  <th>Chat</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {invocations.map((inv) => (
                  <tr key={inv.id}>
                    <td className="cell-date">{new Date(inv.created_at).toLocaleString()}</td>
                    <td>
                      <span
                        className={`status-badge status-badge--${
                          inv.status === 'completed' ? 'success'
                          : inv.status === 'failed' ? 'danger'
                          : inv.status === 'processing' ? 'warning'
                          : 'info'
                        }`}
                      >
                        {inv.status}
                      </span>
                    </td>
                    <td>{inv.source_ip ?? '—'}</td>
                    <td>
                      {inv.chat_id ? (
                        <a
                          href={`/agents/${form.agent_id}/chat?chatId=${inv.chat_id}`}
                          onClick={(e) => { e.preventDefault(); navigate(`/agents/${form.agent_id}/chat?chatId=${inv.chat_id}`); }}
                          style={{ color: '#3b82f6', textDecoration: 'underline', cursor: 'pointer' }}
                        >
                          View chat
                        </a>
                      ) : '—'}
                    </td>
                    <td style={{ color: '#ef4444', fontSize: '13px', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {inv.error_message ?? ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
