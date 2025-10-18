/**
 * ConfirmationDialog Component
 *
 * Modal dialog for confirming high-risk operations in Safe Mode.
 * Displays operation details, risk level, and approve/deny buttons.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Clock, Shield } from 'lucide-react';

export interface ConfirmationRequest {
  token: string;
  tool_name: string;
  capability_id: string;
  operation_description: string;
  risk_level: number;
  timeout_seconds: number;
}

interface ConfirmationDialogProps {
  request: ConfirmationRequest | null;
  onApprove: (token: string) => void;
  onDeny: (token: string) => void;
  autoCloseOnTimeout?: boolean;
}

export function ConfirmationDialog({
  request,
  onApprove,
  onDeny,
  autoCloseOnTimeout = true,
}: ConfirmationDialogProps) {
  const [timeRemaining, setTimeRemaining] = useState<number>(0);
  const [isApproving, setIsApproving] = useState(false);
  const [isDenying, setIsDenying] = useState(false);

  const handleApprove = useCallback(async () => {
    if (!request) return;

    setIsApproving(true);
    try {
      await onApprove(request.token);
    } finally {
      setIsApproving(false);
    }
  }, [onApprove, request]);

  const handleDeny = useCallback(async () => {
    if (!request) return;

    setIsDenying(true);
    try {
      await onDeny(request.token);
    } finally {
      setIsDenying(false);
    }
  }, [onDeny, request]);

  // Update countdown timer
  useEffect(() => {
    if (!request) {
      setTimeRemaining(0);
      return;
    }

    setTimeRemaining(request.timeout_seconds);

    const interval = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          if (autoCloseOnTimeout) {
            // Auto-deny on timeout
            handleDeny();
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [request, autoCloseOnTimeout, handleDeny]);

  const getRiskColor = (riskLevel: number): string => {
    if (riskLevel >= 8) return 'bg-red-500';
    if (riskLevel >= 6) return 'bg-orange-500';
    if (riskLevel >= 4) return 'bg-yellow-500';
    return 'bg-blue-500';
  };

  const getRiskLabel = (riskLevel: number): string => {
    if (riskLevel >= 8) return 'Critical Risk';
    if (riskLevel >= 6) return 'High Risk';
    if (riskLevel >= 4) return 'Medium Risk';
    return 'Low Risk';
  };

  if (!request) return null;

  const isOpen = Boolean(request);
  const riskColor = getRiskColor(request.risk_level);
  const riskLabel = getRiskLabel(request.risk_level);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleDeny()}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-orange-500" />
            High-Risk Operation Confirmation
          </DialogTitle>
          <DialogDescription>
            This operation requires your explicit approval to proceed.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Risk Level Badge */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Risk Level</span>
            </div>
            <span className={`inline-flex items-center rounded px-2 py-1 text-xs font-medium text-white ${riskColor}`}>
              {riskLabel} ({request.risk_level}/10)
            </span>
          </div>

          {/* Operation Details */}
          <div className="rounded-md border border-border/60 bg-muted/40 p-4" role="alert">
            <div className="space-y-2 text-sm">
              <div>
                <span className="font-medium">Tool:</span> {request.tool_name}
              </div>
              <div>
                <span className="font-medium">Capability:</span>{' '}
                {request.capability_id}
              </div>
              <div>
                <span className="font-medium">Operation:</span>{' '}
                {request.operation_description}
              </div>
            </div>
          </div>

          {/* Timeout Warning */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-4 w-4" />
            <span>
              {timeRemaining > 0 ? (
                <>
                  Auto-deny in <strong>{timeRemaining}</strong> seconds
                </>
              ) : (
                <span className="text-orange-500 font-medium">Timeout reached</span>
              )}
            </span>
          </div>

          {/* Warning Message */}
          {request.risk_level >= 8 && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/60 bg-red-500/10 p-4 text-sm text-red-600">
              <AlertTriangle className="mt-0.5 h-4 w-4" />
              <span>
                This is a critical risk operation. Ensure you understand the
                consequences before approving.
              </span>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={handleDeny}
            disabled={isDenying || isApproving}
          >
            {isDenying ? 'Denying...' : 'Deny'}
          </Button>
          <Button
            onClick={handleApprove}
            disabled={isDenying || isApproving || timeRemaining === 0}
            className="bg-orange-500 hover:bg-orange-600"
          >
            {isApproving ? 'Approving...' : 'Approve'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// TODO: Add sound/notification when confirmation request arrives
// TODO: Add keyboard shortcuts (Enter = approve, Esc = deny)
// TODO: Add confirmation history tracking
// TODO: Add "Remember my choice for this operation" checkbox (future feature)
// TODO: Integrate with backend confirmation handler WebSocket events
// TODO: Add animation for countdown timer
