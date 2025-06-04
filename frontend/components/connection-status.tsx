import { Radio, Wifi, WifiOff } from "lucide-react";
import { useAppContext } from "@/context/app-context";
import { WebSocketConnectionState } from "@/typings/agent";

export default function ConnectionStatus() {
  const { state } = useAppContext();
  const { wsConnectionState } = state;

  return (
    <div className="fixed bottom-4 right-4 flex items-center gap-2 bg-black/50 backdrop-blur-sm px-3 py-2 rounded-full">
      {wsConnectionState === WebSocketConnectionState.CONNECTING && (
        <>
          <Radio className="h-4 w-4 text-yellow-400 animate-pulse" />
          <span className="text-yellow-400 text-sm">Connecting...</span>
        </>
      )}
      {wsConnectionState === WebSocketConnectionState.CONNECTED && (
        <>
          <Wifi className="h-4 w-4 text-green-500" />
          <span className="text-green-500 text-sm">Connected</span>
        </>
      )}
      {wsConnectionState === WebSocketConnectionState.DISCONNECTED && (
        <>
          <WifiOff className="h-4 w-4 text-red-500" />
          <span className="text-red-500 text-sm">Disconnected</span>
        </>
      )}
    </div>
  );
}
