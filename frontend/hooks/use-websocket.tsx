import { AgentEvent, WebSocketConnectionState } from "@/typings/agent";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { useAppContext } from "@/context/app-context";

interface WebSocketMessageContent {
  [key: string]: unknown;
}

export function useWebSocket(
  deviceId: string,
  isReplayMode: boolean,
  handleEvent: (
    data: {
      id: string;
      type: AgentEvent;
      content: Record<string, unknown>;
    },
    workspacePath?: string
  ) => void
) {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const { dispatch } = useAppContext();

  const connectWebSocket = () => {
    dispatch({
      type: "SET_WS_CONNECTION_STATE",
      payload: WebSocketConnectionState.CONNECTING,
    });
    const params = new URLSearchParams({ device_id: deviceId });
    const ws = new WebSocket(
      `${process.env.NEXT_PUBLIC_API_URL}/ws?${params.toString()}`
    );

    ws.onopen = () => {
      console.log("WebSocket connection established");
      dispatch({
        type: "SET_WS_CONNECTION_STATE",
        payload: WebSocketConnectionState.CONNECTED,
      });
      // Request workspace info immediately after connection
      ws.send(
        JSON.stringify({
          type: "workspace_info",
          content: {},
        })
      );
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleEvent({ ...data, id: Date.now().toString() });
      } catch (error) {
        console.error("Error parsing WebSocket data:", error);
      }
    };

    ws.onerror = (error) => {
      console.log("WebSocket error:", error);
      dispatch({
        type: "SET_WS_CONNECTION_STATE",
        payload: WebSocketConnectionState.DISCONNECTED,
      });
      toast.error("WebSocket connection error");
    };

    ws.onclose = () => {
      console.log("WebSocket connection closed");
      dispatch({
        type: "SET_WS_CONNECTION_STATE",
        payload: WebSocketConnectionState.DISCONNECTED,
      });
      setSocket(null);
    };

    setSocket(ws);
  };

  const sendMessage = (payload: {
    type: string;
    content: WebSocketMessageContent;
  }) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      toast.error("WebSocket connection is not open. Please try again.");
      return false;
    }

    socket.send(JSON.stringify(payload));
    return true;
  };

  useEffect(() => {
    // Only connect if we have a device ID AND we're not viewing a session history
    if (deviceId && !isReplayMode) {
      connectWebSocket();
    }

    // Clean up the WebSocket connection when the component unmounts
    return () => {
      if (socket) {
        socket.close();
      }
    };
  }, [deviceId, isReplayMode]);

  return { socket, connectWebSocket, sendMessage };
}
