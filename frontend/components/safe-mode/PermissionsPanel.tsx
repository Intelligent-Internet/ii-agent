/**
 * PermissionsPanel Component
 *
 * Displays and manages capability permissions in a matrix view
 *
 * TODO: Integration points
 * - Fetch capability list from WebSocket on mount
 * - Subscribe to capability status updates
 * - Implement grant/revoke capability actions
 * - Add capability search and filtering
 * - Show real-time audit log
 */

import React, { useState, useEffect } from 'react';

interface Capability {
  id: string;
  name: string;
  description: string;
  category: string;
  risk_level: number;
  granted: boolean;
}

interface PermissionsPanelProps {
  sessionId: string;
  onCapabilityToggle?: (capabilityId: string, granted: boolean) => void;
}

export const PermissionsPanel: React.FC<PermissionsPanelProps> = ({
  sessionId,
  onCapabilityToggle,
}) => {
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    // TODO: Fetch capabilities from WebSocket
    // TODO: Subscribe to capability updates
    // Example:
    // const unsubscribe = subscribeToCapabilities(sessionId, (caps) => {
    //   setCapabilities(caps);
    //   setLoading(false);
    // });
    // return () => unsubscribe();

    // Placeholder data
    setCapabilities([]);
    setLoading(false);
  }, [sessionId]);

  const handleToggle = (capabilityId: string, currentlyGranted: boolean) => {
    // TODO: Call API to grant/revoke capability
    // TODO: Update local state optimistically
    // TODO: Handle errors and rollback

    onCapabilityToggle?.(capabilityId, !currentlyGranted);
  };

  const getRiskColor = (riskLevel: number): string => {
    if (riskLevel <= 2) return 'green';
    if (riskLevel <= 5) return 'yellow';
    if (riskLevel <= 7) return 'orange';
    return 'red';
  };

  const filteredCapabilities = capabilities.filter(cap => {
    const matchesCategory = filterCategory === 'all' || cap.category === filterCategory;
    const matchesSearch = cap.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         cap.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const categories = [...new Set(capabilities.map(c => c.category))];

  return (
    <div className="permissions-panel">
      <div className="panel-header">
        <h2>Capability Permissions</h2>
        <div className="panel-controls">
          <input
            type="text"
            placeholder="Search capabilities..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="category-filter"
          >
            <option value="all">All Categories</option>
            {categories.map(cat => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="loading">Loading capabilities...</div>
      ) : (
        <div className="capabilities-list">
          {filteredCapabilities.length === 0 ? (
            <div className="empty-state">No capabilities found</div>
          ) : (
            filteredCapabilities.map(capability => (
              <div key={capability.id} className="capability-row">
                <div className="capability-info">
                  <h3>{capability.name}</h3>
                  <p>{capability.description}</p>
                  <div className="capability-meta">
                    <span className="category">{capability.category}</span>
                    <span className={`risk-badge risk-${getRiskColor(capability.risk_level)}`}>
                      Risk: {capability.risk_level}/10
                    </span>
                  </div>
                </div>
                <div className="capability-actions">
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={capability.granted}
                      onChange={() => handleToggle(capability.id, capability.granted)}
                    />
                    <span className="slider"></span>
                  </label>
                  <span className="grant-status">
                    {capability.granted ? 'Granted' : 'Denied'}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* TODO: Add bulk actions (grant all in category, revoke all, etc.) */}
      {/* TODO: Add export capabilities configuration button */}
    </div>
  );
};

export default PermissionsPanel;
