/**
 * ConsensusIndicator Component
 *
 * Displays real-time consensus analysis for salon conversations
 *
 * TODO: Integration points
 * - Subscribe to consensus updates via WebSocket
 * - Animate consensus level changes
 * - Show detailed consensus points on hover/click
 * - Add export consensus summary button
 */

import React from 'react';

interface ConsensusPoint {
  statement: string;
  supporting_participants: string[];
  confidence: number;
}

interface ConsensusData {
  level: 'none' | 'partial' | 'strong' | 'unanimous';
  consensus_points: ConsensusPoint[];
  areas_of_disagreement: string[];
  synthesis?: string;
  confidence: number;
}

interface ConsensusIndicatorProps {
  salonId: string;
  participantCount: number;
}

export const ConsensusIndicator: React.FC<ConsensusIndicatorProps> = ({
  salonId,
  participantCount,
}) => {
  // TODO: Subscribe to consensus updates
  const [consensusData] = React.useState<ConsensusData>({
    level: 'none',
    consensus_points: [],
    areas_of_disagreement: [],
    confidence: 0,
  });

  const getLevelColor = (level: string): string => {
    switch (level) {
      case 'unanimous': return '#27AE60';  // Green
      case 'strong': return '#2ECC71';     // Light green
      case 'partial': return '#F39C12';    // Orange
      case 'none': return '#95A5A6';       // Gray
      default: return '#95A5A6';
    }
  };

  const getLevelLabel = (level: string): string => {
    switch (level) {
      case 'unanimous': return 'Unanimous Agreement';
      case 'strong': return 'Strong Consensus';
      case 'partial': return 'Partial Agreement';
      case 'none': return 'No Consensus';
      default: return 'Unknown';
    }
  };

  const confidencePercentage = Math.round(consensusData.confidence * 100);

  return (
    <div className="consensus-indicator">
      <div className="consensus-header">
        <h4>Consensus Status</h4>
        <div
          className="consensus-level-badge"
          style={{ backgroundColor: getLevelColor(consensusData.level) }}
        >
          {getLevelLabel(consensusData.level)}
        </div>
        <span className="salon-id text-xs text-muted-foreground">
          Salon: {salonId}
        </span>
      </div>

      <div className="consensus-metrics">
        <div className="metric">
          <span className="metric-label">Confidence:</span>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${confidencePercentage}%`,
                backgroundColor: getLevelColor(consensusData.level),
              }}
            />
          </div>
          <span className="metric-value">{confidencePercentage}%</span>
        </div>
      </div>

      {consensusData.consensus_points.length > 0 && (
        <div className="consensus-points">
          <h5>Points of Agreement</h5>
          {consensusData.consensus_points.map((point, index) => {
            const supportPercent = Math.round(
              (point.supporting_participants.length / participantCount) * 100
            );
            return (
              <div key={index} className="consensus-point">
                <p>{point.statement}</p>
                <div className="point-support">
                  <span className="support-count">
                    {point.supporting_participants.length}/{participantCount} participants
                  </span>
                  <span className="support-percent">({supportPercent}%)</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {consensusData.areas_of_disagreement.length > 0 && (
        <div className="disagreement-areas">
          <h5>Areas of Disagreement</h5>
          {consensusData.areas_of_disagreement.slice(0, 3).map((area, index) => (
            <div key={index} className="disagreement-item">
              <span className="disagreement-icon">⚠️</span>
              <p>{area}</p>
            </div>
          ))}
        </div>
      )}

      {consensusData.synthesis && (
        <div className="consensus-synthesis">
          <h5>Synthesized Position</h5>
          <p>{consensusData.synthesis}</p>
        </div>
      )}

      {/* TODO: Add export button */}
      {/* TODO: Add historical consensus tracking visualization */}
    </div>
  );
};

export default ConsensusIndicator;
