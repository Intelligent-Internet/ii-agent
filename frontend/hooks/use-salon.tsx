/**
 * useSalon hook for managing salon WebSocket interactions
 *
 * Provides methods for:
 * - Starting salon sessions
 * - Sending messages to salons
 * - Getting salon status and consensus
 * - Stopping salon sessions
 *
 * Subscribes to salon events and manages local state
 */

import { useState, useEffect, useCallback } from 'react';

// Salon types
export interface SalonParticipant {
  id: string;
  persona_id: string;
  role: string;
  avatar_color: string;
}

export interface SalonMessage {
  participant_id: string;
  content: string;
  turn_number: number;
  metadata?: Record<string, any>;
  timestamp?: string;
}

export interface SalonStatus {
  salon_id: string;
  state: 'initializing' | 'active' | 'paused' | 'consensus_building' | 'completed' | 'error';
  mode: 'debate' | 'discussion' | 'panel' | 'consensus' | 'brainstorm';
  current_turn: number;
  participants: SalonParticipant[];
  message_count: number;
}

export interface ConsensusPoint {
  statement: string;
  support_percentage: number;
  supporting_participants: string[];
}

export interface SalonConsensus {
  level: 'none' | 'partial' | 'strong' | 'unanimous';
  consensus_points: ConsensusPoint[];
  areas_of_disagreement: string[];
  synthesis?: string;
  confidence: number;
}

export interface UseSalonProps {
  sendMessage: (payload: { type: string; content: any }) => boolean;
  onSalonEvent?: (event: any) => void;
}

export function useSalon({ sendMessage, onSalonEvent }: UseSalonProps) {
  const [salonStatus, setSalonStatus] = useState<SalonStatus | null>(null);
  const [salonMessages, setSalonMessages] = useState<SalonMessage[]>([]);
  const [salonConsensus, setSalonConsensus] = useState<SalonConsensus | null>(null);
  const [isActive, setIsActive] = useState(false);

  // Start a new salon session
  const startSalon = useCallback((
    topic: string,
    options?: {
      context?: string;
      mode?: 'debate' | 'discussion' | 'panel' | 'consensus' | 'brainstorm';
      participant_personas?: string[];
    }
  ) => {
    const success = sendMessage({
      type: 'salon_start',
      content: {
        topic,
        context: options?.context || '',
        mode: options?.mode || 'discussion',
        participant_personas: options?.participant_personas || [
          'dr_research',
          'tech_lead',
          'the_critic',
        ],
      },
    });

    if (success) {
      setIsActive(true);
      setSalonMessages([]);
      setSalonConsensus(null);
    }

    return success;
  }, [sendMessage]);

  // Send a message to the active salon
  const sendSalonMessage = useCallback((
    content: string,
    participantId: string = 'user'
  ) => {
    if (!isActive || !salonStatus) {
      console.warn('No active salon session');
      return false;
    }

    return sendMessage({
      type: 'salon_send_message',
      content: {
        participant_id: participantId,
        content,
        turn_number: salonStatus.current_turn,
        metadata: {},
      },
    });
  }, [sendMessage, isActive, salonStatus]);

  // Request current salon status
  const getSalonStatus = useCallback(() => {
    if (!isActive) {
      console.warn('No active salon session');
      return false;
    }

    return sendMessage({
      type: 'salon_get_status',
      content: {},
    });
  }, [sendMessage, isActive]);

  // Trigger consensus analysis
  const getConsensus = useCallback(() => {
    if (!isActive) {
      console.warn('No active salon session');
      return false;
    }

    return sendMessage({
      type: 'salon_get_consensus',
      content: {},
    });
  }, [sendMessage, isActive]);

  // Stop the current salon session
  const stopSalon = useCallback(() => {
    if (!isActive) {
      console.warn('No active salon session');
      return false;
    }

    const success = sendMessage({
      type: 'salon_stop',
      content: {},
    });

    if (success) {
      setIsActive(false);
    }

    return success;
  }, [sendMessage, isActive]);

  // Handle salon events from WebSocket
  const handleSalonEvent = useCallback((event: any) => {
    const { type, content } = event;

    switch (type) {
      case 'salon_started':
        console.log('Salon started:', content);
        setIsActive(true);
        if (onSalonEvent) onSalonEvent(event);
        break;

      case 'salon_message':
        console.log('Salon message:', content);
        setSalonMessages((prev) => [...prev, content as SalonMessage]);
        if (onSalonEvent) onSalonEvent(event);
        break;

      case 'salon_status':
        console.log('Salon status update:', content);
        setSalonStatus(content as SalonStatus);
        if (onSalonEvent) onSalonEvent(event);
        break;

      case 'salon_consensus':
        console.log('Salon consensus update:', content);
        setSalonConsensus(content as SalonConsensus);
        if (onSalonEvent) onSalonEvent(event);
        break;

      case 'salon_ended':
        console.log('Salon ended:', content);
        setIsActive(false);
        if (onSalonEvent) onSalonEvent(event);
        break;

      case 'salon_error':
        console.error('Salon error:', content);
        if (onSalonEvent) onSalonEvent(event);
        break;

      default:
        // Not a salon event
        break;
    }
  }, [onSalonEvent]);

  return {
    // State
    salonStatus,
    salonMessages,
    salonConsensus,
    isActive,

    // Actions
    startSalon,
    sendSalonMessage,
    getSalonStatus,
    getConsensus,
    stopSalon,

    // Event handler (to be called from parent component's event handler)
    handleSalonEvent,
  };
}
