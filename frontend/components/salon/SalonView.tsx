/**
 * SalonView Component
 *
 * Main view for multi-LLM salon conversations
 *
 * TODO: Integration points
 * - Connect to WebSocket for salon events
 * - Implement real-time message streaming
 * - Add voice playback for each participant
 * - Handle turn coordination visualization
 * - Integrate consensus indicator updates
 */

import React, { useState, useEffect } from 'react';

interface SalonParticipant {
  id: string;
  persona_id: string;
  name: string;
  role: string;
  avatar_color: string;
  is_speaking: boolean;
}

interface SalonMessage {
  id: string;
  participant_id: string;
  content: string;
  turn_number: number;
  timestamp: string;
}

interface SalonViewProps {
  salonId: string;
  onExit?: () => void;
}

export const SalonView: React.FC<SalonViewProps> = ({ salonId, onExit }) => {
  const [participants, setParticipants] = useState<SalonParticipant[]>([]);
  const [messages, setMessages] = useState<SalonMessage[]>([]);
  const [currentTurn, setCurrentTurn] = useState(0);
  const [mode, setMode] = useState<string>('discussion');
  const [state, setState] = useState<string>('initializing');

  useEffect(() => {
    // TODO: Subscribe to salon WebSocket events
    // TODO: Fetch initial salon state
    // Example:
    // const unsubscribe = subscribeToSalon(salonId, {
    //   onMessage: (msg) => setMessages(prev => [...prev, msg]),
    //   onStatusUpdate: (status) => { setState(status.state); setCurrentTurn(status.current_turn); },
    //   onParticipantUpdate: (parts) => setParticipants(parts),
    // });
    // return () => unsubscribe();

    // Placeholder resets to mark hooks as in-use until live data is wired.
    setParticipants([]);
    setMessages([]);
    setCurrentTurn(0);
    setMode('discussion');
    setState('initializing');
  }, [salonId]);

  return (
    <div className="salon-view">
      <div className="salon-header">
        <h1>Cognitive Salon</h1>
        <div className="salon-metadata">
          <span className="mode-badge">{mode}</span>
          <span className="turn-counter">Turn {currentTurn}</span>
          <span className={`state-indicator state-${state}`}>{state}</span>
        </div>
        {onExit && (
          <button onClick={onExit} className="btn-exit">Exit Salon</button>
        )}
      </div>

      <div className="salon-content">
        {/* Participants sidebar */}
        <div className="participants-sidebar">
          <h3>Participants</h3>
          {participants.map(participant => (
            <div
              key={participant.id}
              className={`participant-card ${participant.is_speaking ? 'speaking' : ''}`}
              style={{ borderLeft: `4px solid ${participant.avatar_color}` }}
            >
              <div className="participant-avatar" style={{ backgroundColor: participant.avatar_color }}>
                {participant.name.charAt(0)}
              </div>
              <div className="participant-info">
                <h4>{participant.name}</h4>
                <p>{participant.role}</p>
              </div>
              {participant.is_speaking && (
                <div className="speaking-indicator">🎤</div>
              )}
            </div>
          ))}
        </div>

        {/* Conversation flow */}
        <div className="conversation-flow">
          {messages.length === 0 ? (
            <div className="empty-state">Waiting for salon to begin...</div>
          ) : (
            messages.map(message => {
              const participant = participants.find(p => p.id === message.participant_id);
              return (
                <div key={message.id} className="salon-message">
                  <div className="message-header">
                    <span
                      className="message-avatar"
                      style={{ backgroundColor: participant?.avatar_color }}
                    >
                      {participant?.name.charAt(0) || '?'}
                    </span>
                    <span className="message-author">{participant?.name || 'Unknown'}</span>
                    <span className="message-turn">Turn {message.turn_number}</span>
                    <span className="message-timestamp">
                      {new Date(message.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="message-content">{message.content}</div>
                </div>
              );
            })
          )}
        </div>

        {/* Consensus indicator */}
        <div className="consensus-panel">
          <h3>Consensus Tracker</h3>
          {/* TODO: Add ConsensusIndicator component */}
          <div className="consensus-placeholder">
            Consensus analysis will appear here
          </div>
        </div>
      </div>

      {/* TODO: Add SalonControls component for pause/resume/mode switching */}
    </div>
  );
};

export default SalonView;
