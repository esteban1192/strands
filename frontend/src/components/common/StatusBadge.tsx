import './StatusBadge.css';

interface StatusBadgeProps {
  status?: string;
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
}

const AUTO_VARIANT: Record<string, StatusBadgeProps['variant']> = {
  active: 'success',
  inactive: 'neutral',
  paused: 'warning',
  unknown: 'neutral',
  true: 'success',
  false: 'neutral',
};

export default function StatusBadge({ status, variant }: StatusBadgeProps) {
  const displayStatus = status || 'unknown';
  const resolved = variant ?? AUTO_VARIANT[displayStatus.toLowerCase()] ?? 'info';
  return <span className={`status-badge status-badge--${resolved}`}>{displayStatus}</span>;
}
