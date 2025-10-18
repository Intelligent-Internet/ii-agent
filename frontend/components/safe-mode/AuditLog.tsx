/**
 * AuditLog Component
 *
 * Displays real-time audit log of permission checks and tool executions
 *
 * TODO: Integration points
 * - Subscribe to audit log WebSocket events
 * - Implement real-time log streaming
 * - Add export to CSV/JSON functionality
 * - Implement log filtering and search
 * - Add pagination for large logs
 */

import React, { useState, useEffect, useRef } from 'react';

interface AuditEntry {
  timestamp: string;
  tool_name: string;
  capability_id: string;
  action: 'allowed' | 'denied' | 'granted' | 'revoked' | 'confirmed';
  reason?: string;
  user_id?: string;
  session_id?: string;
}

interface AuditLogProps {
  sessionId: string;
  maxEntries?: number;
  autoScroll?: boolean;
}

export const AuditLog: React.FC<AuditLogProps> = ({
  sessionId,
  maxEntries = 100,
  autoScroll = true,
}) => {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // TODO: Subscribe to audit log WebSocket events
    // Example:
    // const unsubscribe = subscribeToAuditLog(sessionId, (newEntry) => {
    //   setEntries(prev => [...prev, newEntry].slice(-maxEntries));
    // });
    // return () => unsubscribe();
  }, [sessionId, maxEntries]);

  useEffect(() => {
    if (autoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [entries, autoScroll]);

  const getActionIcon = (action: string): string => {
    switch (action) {
      case 'allowed': return '✓';
      case 'denied': return '✗';
      case 'granted': return '➕';
      case 'revoked': return '➖';
      case 'confirmed': return '✓';
      default: return '•';
    }
  };

  const getActionColor = (action: string): string => {
    switch (action) {
      case 'allowed': return 'green';
      case 'denied': return 'red';
      case 'granted': return 'blue';
      case 'revoked': return 'orange';
      case 'confirmed': return 'purple';
      default: return 'gray';
    }
  };

  const filteredEntries = entries.filter(entry => {
    if (filter === 'all') return true;
    return entry.action === filter;
  });

  const handleExport = () => {
    // TODO: Implement export to CSV/JSON
    console.log('Export audit log', entries);
  };

  const handleClear = () => {
    // TODO: Confirm with user before clearing
    // TODO: Call API to clear audit log
    setEntries([]);
  };

  return (
    <div className="audit-log">
      <div className="audit-log-header">
        <h3>Audit Log</h3>
        <div className="audit-log-controls">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Actions</option>
            <option value="allowed">Allowed</option>
            <option value="denied">Denied</option>
            <option value="granted">Granted</option>
            <option value="revoked">Revoked</option>
          </select>
          <button onClick={handleExport} className="btn-export">
            Export
          </button>
          <button onClick={handleClear} className="btn-clear">
            Clear
          </button>
        </div>
      </div>

      <div className="audit-log-entries">
        {filteredEntries.length === 0 ? (
          <div className="empty-state">No audit entries yet</div>
        ) : (
          filteredEntries.map((entry, index) => (
            <div
              key={`${entry.timestamp}-${index}`}
              className={`audit-entry audit-entry-${getActionColor(entry.action)}`}
            >
              <span className="entry-icon">{getActionIcon(entry.action)}</span>
              <span className="entry-timestamp">
                {new Date(entry.timestamp).toLocaleTimeString()}
              </span>
              <span className="entry-tool">{entry.tool_name}</span>
              <span className="entry-capability">{entry.capability_id}</span>
              <span className={`entry-action action-${getActionColor(entry.action)}`}>
                {entry.action}
              </span>
              {entry.reason && (
                <span className="entry-reason" title={entry.reason}>
                  {entry.reason}
                </span>
              )}
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>

      {/* TODO: Add statistics summary (total allowed/denied, etc.) */}
      {/* TODO: Add time range selector */}
    </div>
  );
};

export default AuditLog;
