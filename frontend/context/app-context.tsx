"use client";

import { createContext, useContext, useReducer, ReactNode } from "react";
import {
  ActionStep,
  AgentEvent,
  AVAILABLE_MODELS,
  Message,
  TAB,
  ToolSettings,
  WebSocketConnectionState,
} from "@/typings/agent";

// Define the state interface
interface AppState {
  messages: Message[];
  isLoading: boolean;
  activeTab: TAB;
  currentActionData?: ActionStep;
  activeFileCodeEditor: string;
  currentQuestion: string;
  isCompleted: boolean;
  isStopped: boolean;
  workspaceInfo: string;
  isUploading: boolean;
  uploadedFiles: string[];
  filesContent: { [key: string]: string };
  browserUrl: string;
  isGeneratingPrompt: boolean;
  editingMessage?: Message;
  toolSettings: ToolSettings;
  selectedModel?: string;
  wsConnectionState: WebSocketConnectionState;
}

// Define action types
type AppAction =
  | { type: "SET_MESSAGES"; payload: Message[] }
  | { type: "ADD_MESSAGE"; payload: Message }
  | { type: "UPDATE_MESSAGE"; payload: Message }
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "SET_ACTIVE_TAB"; payload: TAB }
  | { type: "SET_CURRENT_ACTION_DATA"; payload: ActionStep | undefined }
  | { type: "SET_ACTIVE_FILE"; payload: string }
  | { type: "SET_CURRENT_QUESTION"; payload: string }
  | { type: "SET_COMPLETED"; payload: boolean }
  | { type: "SET_STOPPED"; payload: boolean }
  | { type: "SET_WORKSPACE_INFO"; payload: string }
  | { type: "SET_IS_UPLOADING"; payload: boolean }
  | { type: "SET_UPLOADED_FILES"; payload: string[] }
  | { type: "ADD_UPLOADED_FILES"; payload: string[] }
  | { type: "SET_FILES_CONTENT"; payload: { [key: string]: string } }
  | { type: "ADD_FILE_CONTENT"; payload: { path: string; content: string } }
  | { type: "SET_BROWSER_URL"; payload: string }
  | { type: "SET_GENERATING_PROMPT"; payload: boolean }
  | { type: "SET_EDITING_MESSAGE"; payload: Message | undefined }
  | { type: "SET_TOOL_SETTINGS"; payload: AppState["toolSettings"] }
  | { type: "SET_SELECTED_MODEL"; payload: string | undefined }
  | { type: "SET_WS_CONNECTION_STATE"; payload: WebSocketConnectionState }
  | {
      type: "HANDLE_EVENT";
      payload: {
        event: AgentEvent;
        data: Record<string, unknown>;
        workspacePath?: string;
      };
    };

// Initial state
const initialState: AppState = {
  messages: [],
  isLoading: false,
  activeTab: TAB.BROWSER,
  activeFileCodeEditor: "",
  currentQuestion: "",
  isCompleted: false,
  isStopped: false,
  workspaceInfo: "",
  isUploading: false,
  uploadedFiles: [],
  filesContent: {},
  browserUrl: "",
  isGeneratingPrompt: false,
  toolSettings: {
    deep_research: false,
    pdf: true,
    media_generation: true,
    audio_generation: true,
    browser: true,
    thinking_tokens: 10000,
  },
  wsConnectionState: WebSocketConnectionState.CONNECTING,
  selectedModel: AVAILABLE_MODELS[0],
};

// Create the context
const AppContext = createContext<{
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
}>({
  state: initialState,
  dispatch: () => null,
});

// Reducer function
function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_MESSAGES":
      return { ...state, messages: action.payload };
    case "ADD_MESSAGE":
      return { ...state, messages: [...state.messages, action.payload] };
    case "UPDATE_MESSAGE":
      return {
        ...state,
        messages: state.messages.map((message) =>
          message.id === action.payload.id ? action.payload : message
        ),
      };
    case "SET_LOADING":
      return { ...state, isLoading: action.payload };
    case "SET_ACTIVE_TAB":
      return { ...state, activeTab: action.payload };
    case "SET_CURRENT_ACTION_DATA":
      return { ...state, currentActionData: action.payload };
    case "SET_ACTIVE_FILE":
      return { ...state, activeFileCodeEditor: action.payload };
    case "SET_CURRENT_QUESTION":
      return { ...state, currentQuestion: action.payload };
    case "SET_COMPLETED":
      return { ...state, isCompleted: action.payload };
    case "SET_STOPPED":
      return { ...state, isStopped: action.payload };
    case "SET_WORKSPACE_INFO":
      return { ...state, workspaceInfo: action.payload };
    case "SET_IS_UPLOADING":
      return { ...state, isUploading: action.payload };
    case "SET_UPLOADED_FILES":
      return { ...state, uploadedFiles: action.payload };
    case "ADD_UPLOADED_FILES":
      return {
        ...state,
        uploadedFiles: [...state.uploadedFiles, ...action.payload],
      };
    case "SET_FILES_CONTENT":
      return { ...state, filesContent: action.payload };
    case "ADD_FILE_CONTENT":
      return {
        ...state,
        filesContent: {
          ...state.filesContent,
          [action.payload.path]: action.payload.content,
        },
      };
    case "SET_BROWSER_URL":
      return { ...state, browserUrl: action.payload };
    case "SET_GENERATING_PROMPT":
      return { ...state, isGeneratingPrompt: action.payload };
    case "SET_EDITING_MESSAGE":
      return { ...state, editingMessage: action.payload };
    case "SET_TOOL_SETTINGS":
      return { ...state, toolSettings: action.payload };
    case "SET_SELECTED_MODEL":
      return { ...state, selectedModel: action.payload };
    case "SET_WS_CONNECTION_STATE":
      return { ...state, wsConnectionState: action.payload };
    default:
      return state;
  }
}

// Context provider component
export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

// Custom hook to use the context
export function useAppContext() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error("useAppContext must be used within an AppProvider");
  }
  return context;
}
