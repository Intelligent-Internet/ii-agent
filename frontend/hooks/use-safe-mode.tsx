/**
 * React hook for managing Safe Mode state and capabilities.
 *
 * This hook provides real-time synchronization with the backend Safe Mode system,
 * allowing components to:
 * - Get current safe mode status and profile
 * - List all capabilities with grant status
 * - Grant and revoke capabilities
 * - View audit log entries
 * - Subscribe to safe mode events via WebSocket
 */

import { useState, useEffect, useCallback } from 'react';

export interface SafeModeStatus {
  profile: string;
  granted_capabilities: string[];
  high_risk_threshold: number;
  require_confirmation: boolean;
}

export interface Capability {
  id: string;
  name: string;
  description: string;
  category: string;
  risk_level: number;
  granted: boolean;
}

export interface AuditLogEntry {
  timestamp: string;
  tool_name: string;
  capability_id: string;
  action: string;
  reason?: string;
}

interface UseSafeModeProps {
  socket: WebSocket | null;
  onEvent?: (type: string, content: Record<string, unknown>) => void;
}

export function useSafeMode({ socket, onEvent }: UseSafeModeProps) {
  const [status, setStatus] = useState<SafeModeStatus | null>(null);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Send WebSocket message helper
  const sendMessage = useCallback(
    (type: string, content: Record<string, unknown> = {}) => {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        console.error('WebSocket not connected');
        setError('WebSocket connection not available');
        return false;
      }

      try {
        socket.send(JSON.stringify({ type, content }));
        return true;
      } catch (err) {
        console.error('Error sending WebSocket message:', err);
        setError('Failed to send message');
        return false;
      }
    },
    [socket]
  );

  // Request current safe mode status
  const getStatus = useCallback(() => {
    setLoading(true);
    setError(null);
    sendMessage('safe_mode_get_status');
  }, [sendMessage]);

  // Set safe mode profile
  const setProfile = useCallback(
    (profile: string) => {
      setLoading(true);
      setError(null);
      sendMessage('safe_mode_set_profile', { profile });
    },
    [sendMessage]
  );

  // Request all capabilities
  const getCapabilities = useCallback(() => {
    setLoading(true);
    setError(null);
    sendMessage('safe_mode_get_capabilities');
  }, [sendMessage]);

  // Grant a capability
  const grantCapability = useCallback(
    (capability_id: string) => {
      setLoading(true);
      setError(null);
      sendMessage('safe_mode_grant_capability', { capability_id });
    },
    [sendMessage]
  );

  // Revoke a capability
  const revokeCapability = useCallback(
    (capability_id: string) => {
      setLoading(true);
      setError(null);
      sendMessage('safe_mode_revoke_capability', { capability_id });
    },
    [sendMessage]
  );

  // Request audit log
  const getAuditLog = useCallback(() => {
    setLoading(true);
    setError(null);
    sendMessage('safe_mode_get_audit_log');
  }, [sendMessage]);

  // Handle WebSocket events
  useEffect(() => {
    if (!socket) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        const { type, content } = data;

        // Call custom event handler if provided
        if (onEvent) {
          onEvent(type, content);
        }

        // Handle safe mode events
        switch (type) {
          case 'safe_mode_status':
            setStatus(content as SafeModeStatus);
            setLoading(false);
            break;

          case 'safe_mode_capabilities':
            setCapabilities(content.capabilities as Capability[]);
            setLoading(false);
            break;

          case 'safe_mode_audit_log':
            setAuditLog(content.entries as AuditLogEntry[]);
            setLoading(false);
            break;

          case 'error':
            if (content.message) {
              setError(content.message as string);
            }
            setLoading(false);
            break;

          default:
            // Ignore other event types
            break;
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    socket.addEventListener('message', handleMessage);

    return () => {
      socket.removeEventListener('message', handleMessage);
    };
  }, [socket, onEvent]);

  // Auto-fetch status on mount
  useEffect(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      getStatus();
      getCapabilities();
    }
  }, [socket]); // Note: Intentionally not including getStatus/getCapabilities to avoid loops

  return {
    // State
    status,
    capabilities,
    auditLog,
    loading,
    error,

    // Actions
    getStatus,
    setProfile,
    getCapabilities,
    grantCapability,
    revokeCapability,
    getAuditLog,
  };
}

// TODO: Add confirmation dialog support when backend confirmation workflow is ready
// TODO: Add optimistic updates for grant/revoke operations
// TODO: Add capability filtering and search helpers
// TODO: Add audit log export functionality
// TODO: Integrate with settings persistence
