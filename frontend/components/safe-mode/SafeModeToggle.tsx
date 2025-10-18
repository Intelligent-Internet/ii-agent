/**
 * SafeModeToggle Component
 *
 * Quick toggle for switching between safe mode profiles
 *
 * TODO: Integration points
 * - Connect to WebSocket for safe mode status updates
 * - Implement profile switching API calls
 * - Add confirmation dialog for high-risk profile changes
 * - Integrate with settings context
 */

import React, { useState } from 'react';

interface SafeModeToggleProps {
  currentProfile: 'read_only' | 'restricted' | 'standard' | 'full' | 'custom';
  onProfileChange: (profile: string) => void;
  disabled?: boolean;
}

export const SafeModeToggle: React.FC<SafeModeToggleProps> = ({
  currentProfile,
  onProfileChange,
  disabled = false,
}) => {
  const [isChanging, setIsChanging] = useState(false);

  const profiles = [
    { id: 'read_only', label: 'Read Only', color: 'green', riskLevel: 'Safe' },
    { id: 'restricted', label: 'Restricted', color: 'blue', riskLevel: 'Low Risk' },
    { id: 'standard', label: 'Standard', color: 'yellow', riskLevel: 'Medium Risk' },
    { id: 'full', label: 'Full Access', color: 'red', riskLevel: 'High Risk' },
  ];

  const handleProfileChange = async (newProfile: string) => {
    // TODO: Add confirmation dialog for high-risk profiles
    // TODO: Call API to update safe mode profile
    // TODO: Handle WebSocket reconnection if needed

    setIsChanging(true);
    try {
      // Placeholder for API call
      // await updateSafeModeProfile(newProfile);
      onProfileChange(newProfile);
    } catch (error) {
      console.error('Failed to change safe mode profile:', error);
      // TODO: Show error notification
    } finally {
      setIsChanging(false);
    }
  };

  const currentProfileInfo = profiles.find(p => p.id === currentProfile);

  return (
    <div className="safe-mode-toggle">
      <div className="safe-mode-status">
        <span className={`status-indicator status-${currentProfileInfo?.color}`}>
          {currentProfileInfo?.label || 'Unknown'}
        </span>
        <span className="risk-level">{currentProfileInfo?.riskLevel}</span>
      </div>

      <select
        value={currentProfile}
        onChange={(e) => handleProfileChange(e.target.value)}
        disabled={disabled || isChanging}
        className="profile-selector"
      >
        {profiles.map(profile => (
          <option key={profile.id} value={profile.id}>
            {profile.label} - {profile.riskLevel}
          </option>
        ))}
      </select>

      {/* TODO: Add visual indicator for active capabilities count */}
      {/* TODO: Add quick access to permissions panel */}
    </div>
  );
};

export default SafeModeToggle;
