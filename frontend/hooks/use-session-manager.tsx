import { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import { AgentEvent, Message, IEvent } from "@/typings/agent";
import { useAppContext } from "@/context/app-context";

export function useSessionManager({
  searchParams,
  handleEvent,
}: {
  searchParams: URLSearchParams;
  handleEvent: (
    data: { id: string; type: AgentEvent; content: Record<string, unknown> },
    workspacePath?: string,
    ignoreClickAction?: boolean
  ) => void;
}) {
  const { dispatch } = useAppContext();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const eventsDataRef = useRef<{ events: IEvent[]; workspace: string } | null>(
    null
  );
  const delayTimeRef = useRef<number>(1500);

  const isReplayMode = !!searchParams.get("id");

  // Get session ID from URL params
  useEffect(() => {
    const id = searchParams.get("id");
    setSessionId(id);
  }, [searchParams]);

  const processAllEventsImmediately = () => {
    delayTimeRef.current = 0;
  };

  const fetchSessionEvents = useCallback(async () => {
    const id = searchParams.get("id");
    if (!id) return;

    setIsLoadingSession(true);
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/sessions/${id}/events`
      );

      if (!response.ok) {
        throw new Error(
          `Error fetching session events: ${response.statusText}`
        );
      }

      const data = await response.json();
      const workspace = data.events?.[0]?.workspace_dir;
      dispatch({ type: "SET_WORKSPACE_INFO", payload: workspace });

      if (data.events && Array.isArray(data.events)) {
        // Store events data for potential immediate processing
        eventsDataRef.current = { events: data.events, workspace };

        // Process events to reconstruct the conversation
        const reconstructedMessages: Message[] = [];

        // Function to process events with delay
        const processEventsWithDelay = async () => {
          dispatch({ type: "SET_LOADING", payload: true });
          for (let i = 0; i < data.events.length; i++) {
            const event = data.events[i];
            if (delayTimeRef.current > 0) {
              await new Promise((resolve) =>
                setTimeout(resolve, delayTimeRef.current)
              );
            }

            handleEvent(
              { ...event.event_payload, id: event.id },
              workspace,
              delayTimeRef.current === 0
            );
          }
          dispatch({ type: "SET_LOADING", payload: false });
        };

        // Start processing events with delay
        processEventsWithDelay();

        // Set the reconstructed messages
        if (reconstructedMessages.length > 0) {
          dispatch({ type: "SET_MESSAGES", payload: reconstructedMessages });
          dispatch({ type: "SET_COMPLETED", payload: true });
        }

        // Extract workspace info if available
        const workspaceEvent = data.events.find(
          (e: IEvent) => e.event_type === AgentEvent.WORKSPACE_INFO
        );
        if (workspaceEvent && workspaceEvent.event_payload.path) {
          dispatch({ type: "SET_WORKSPACE_INFO", payload: workspace });
        }
      }
    } catch (error) {
      console.error("Failed to fetch session events:", error);
      toast.error("Failed to load session history");
    } finally {
      setIsLoadingSession(false);
    }
  }, [searchParams]);

  useEffect(() => {
    fetchSessionEvents();
  }, [fetchSessionEvents]);

  return {
    sessionId,
    isLoadingSession,
    isReplayMode,
    setSessionId,
    fetchSessionEvents,
    processAllEventsImmediately,
  };
}
