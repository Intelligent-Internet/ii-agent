"use client";

import { RefObject, useEffect, useRef, useCallback } from "react";
import { cloneDeep, debounce } from "lodash";
import { toast } from "sonner";

import { AppAction, useAppContext } from "@/context/app-context";
import { AgentEvent, TOOL, ActionStep, Message, TAB } from "@/typings/agent";
import { Terminal as XTerm } from "@xterm/xterm";

export function useAppEvents({
  xtermRef,
}: {
  xtermRef: RefObject<XTerm | null>;
}) {
  const { state, dispatch } = useAppContext();
  const messagesRef = useRef(state.messages);

  useEffect(() => {
    messagesRef.current = state.messages;
  }, [state.messages]);

  // Create a custom dispatch function that updates messagesRef immediately
  const safeDispatch = useCallback(
    (action: AppAction) => {
      // If the action is adding a message, update our ref immediately
      if (action.type === "ADD_MESSAGE") {
        messagesRef.current = [...messagesRef.current, action.payload];
      } else if (action.type === "UPDATE_MESSAGE") {
        messagesRef.current = messagesRef.current.map((msg) =>
          msg.id === action.payload.id ? action.payload : msg
        );
      } else if (action.type === "SET_MESSAGES") {
        messagesRef.current = action.payload;
      }

      // Call the actual dispatch
      dispatch(action);
    },
    [dispatch]
  );

  const handleEvent = useCallback(
    (
      data: {
        id: string;
        type: AgentEvent;
        content: Record<string, unknown>;
      },
      workspacePath?: string,
      ignoreClickAction?: boolean
    ) => {
      switch (data.type) {
        case AgentEvent.AGENT_INITIALIZED:
          safeDispatch({ type: "SET_AGENT_INITIALIZED", payload: true });
          break;

        case AgentEvent.SYSTEM:
          if (data.content.type === "reviewer_agent") {
            safeDispatch({
              type: "ADD_MESSAGE",
              payload: {
                id: data.id,
                role: "assistant",
                action: {
                  type: TOOL.REVIEWER_AGENT,
                  data: {
                    content: data.content.message as string,
                  },
                },
                timestamp: Date.now(),
              },
            });
          } else {
            safeDispatch({
              type: "ADD_MESSAGE",
              payload: {
                id: data.id,
                role: "assistant",
                content: data.content.message as string,
                timestamp: Date.now(),
              },
            });
          }
          break;

        case AgentEvent.USER_MESSAGE:
          safeDispatch({
            type: "ADD_MESSAGE",
            payload: {
              id: data.id,
              role: "user",
              content: data.content.text as string,
              timestamp: Date.now(),
            },
          });
          break;

        case AgentEvent.PROMPT_GENERATED:
          safeDispatch({ type: "SET_GENERATING_PROMPT", payload: false });
          safeDispatch({
            type: "SET_CURRENT_QUESTION",
            payload: data.content.result as string,
          });
          break;

        case AgentEvent.PROCESSING:
          safeDispatch({ type: "SET_LOADING", payload: true });
          break;

        case AgentEvent.WORKSPACE_INFO:
          safeDispatch({
            type: "SET_WORKSPACE_INFO",
            payload: data.content.path as string,
          });
          break;

        case AgentEvent.AGENT_THINKING:
          safeDispatch({
            type: "ADD_MESSAGE",
            payload: {
              id: data.id,
              role: "assistant",
              content: data.content.text as string,
              timestamp: Date.now(),
            },
          });
          break;

        case AgentEvent.TOOL_CALL:
          if (data.content.tool_name === TOOL.SEQUENTIAL_THINKING) {
            safeDispatch({
              type: "ADD_MESSAGE",
              payload: {
                id: data.id,
                role: "assistant",
                content: (data.content.tool_input as { thought: string })
                  .thought as string,
                timestamp: Date.now(),
              },
            });
          } else if (data.content.tool_name === TOOL.MESSAGE_USER) {
            safeDispatch({
              type: "ADD_MESSAGE",
              payload: {
                id: data.id,
                role: "assistant",
                content: (data.content.tool_input as { text: string })
                  .text as string,
                timestamp: Date.now(),
              },
            });
          } else {
            const message: Message = {
              id: data.id,
              role: "assistant",
              action: {
                type: data.content.tool_name as TOOL,
                data: data.content,
              },
              timestamp: Date.now(),
            };
            const url = (data.content.tool_input as { url: string })
              ?.url as string;
            if (url) {
              safeDispatch({ type: "SET_BROWSER_URL", payload: url });
            }
            safeDispatch({ type: "ADD_MESSAGE", payload: message });
            if (!ignoreClickAction) {
              handleClickAction(message.action);
            }
          }
          break;

        case AgentEvent.FILE_EDIT:
          // Get the latest messages from our ref to ensure we have the most up-to-date state
          const messages = [...messagesRef.current];
          const lastMessage = cloneDeep(messages[messages.length - 1]);

          if (
            lastMessage?.action &&
            lastMessage.action.type === TOOL.STR_REPLACE_EDITOR
          ) {
            lastMessage.action.data.content = data.content.content as string;
            lastMessage.action.data.path = data.content.path as string;
            const workspace = workspacePath || state.workspaceInfo;
            const filePath = (data.content.path as string)?.includes(workspace)
              ? (data.content.path as string)
              : `${workspace}/${data.content.path}`;

            safeDispatch({
              type: "ADD_FILE_CONTENT",
              payload: {
                path: filePath,
                content: data.content.content as string,
              },
            });

            if (!ignoreClickAction) {
              setTimeout(() => {
                handleClickAction(lastMessage.action);
              }, 500);
            }
            safeDispatch({
              type: "UPDATE_MESSAGE",
              payload: lastMessage,
            });
          }
          break;

        case AgentEvent.BROWSER_USE:
          // Commented out in original code
          break;

        case AgentEvent.TOOL_RESULT:
          if (data.content.tool_name === TOOL.BROWSER_USE) {
            safeDispatch({
              type: "ADD_MESSAGE",
              payload: {
                id: data.id,
                role: "assistant",
                content: data.content.result as string,
                timestamp: Date.now(),
              },
            });
          } else {
            if (
              data.content.tool_name !== TOOL.SEQUENTIAL_THINKING &&
              data.content.tool_name !== TOOL.PRESENTATION &&
              data.content.tool_name !== TOOL.MESSAGE_USER &&
              data.content.tool_name !== TOOL.RETURN_CONTROL_TO_USER
            ) {
              // Get the latest messages from our ref
              const messages = [...messagesRef.current];
              const lastMessage = cloneDeep(messages[messages.length - 1]);

              if (
                lastMessage?.action &&
                lastMessage.action?.type === data.content.tool_name
              ) {
                lastMessage.action.data.result = `${data.content.result}`;
                if (
                  [
                    TOOL.BROWSER_VIEW,
                    TOOL.BROWSER_CLICK,
                    TOOL.BROWSER_ENTER_TEXT,
                    TOOL.BROWSER_PRESS_KEY,
                    TOOL.BROWSER_GET_SELECT_OPTIONS,
                    TOOL.BROWSER_SELECT_DROPDOWN_OPTION,
                    TOOL.BROWSER_SWITCH_TAB,
                    TOOL.BROWSER_OPEN_NEW_TAB,
                    TOOL.BROWSER_WAIT,
                    TOOL.BROWSER_SCROLL_DOWN,
                    TOOL.BROWSER_SCROLL_UP,
                    TOOL.BROWSER_NAVIGATION,
                    TOOL.BROWSER_RESTART,
                  ].includes(data.content.tool_name as TOOL)
                ) {
                  lastMessage.action.data.result =
                    data.content.result && Array.isArray(data.content.result)
                      ? data.content.result.find(
                          (item) => item.type === "image"
                        )?.source?.data
                      : undefined;
                }
                lastMessage.action.data.isResult = true;
                if (!ignoreClickAction) {
                  setTimeout(() => {
                    handleClickAction(lastMessage.action);
                  }, 500);
                }

                safeDispatch({
                  type: "UPDATE_MESSAGE",
                  payload: lastMessage,
                });
              } else {
                safeDispatch({
                  type: "ADD_MESSAGE",
                  payload: {
                    ...lastMessage,
                    action: data.content as ActionStep,
                  },
                });
              }
            }
          }
          break;

        case AgentEvent.AGENT_RESPONSE:
          // safeDispatch({
          //   type: "ADD_MESSAGE",
          //   payload: {
          //     id: Date.now().toString(),
          //     role: "assistant",
          //     content: data.content.text as string,
          //     timestamp: Date.now(),
          //   },
          // });
          safeDispatch({ type: "SET_COMPLETED", payload: true });
          safeDispatch({ type: "SET_LOADING", payload: false });
          break;

        case AgentEvent.UPLOAD_SUCCESS:
          safeDispatch({ type: "SET_IS_UPLOADING", payload: false });

          // Update the uploaded files state
          const newFiles = data.content.files as {
            path: string;
            saved_path: string;
          }[];

          // Filter out files that are part of folders
          const folderMetadataFiles = newFiles.filter((f) =>
            f.path.startsWith("folder:")
          );

          const folderNames = folderMetadataFiles
            .map((f) => {
              const match = f.path.match(/^folder:(.+):\d+$/);
              return match ? match[1] : null;
            })
            .filter(Boolean) as string[];

          // Only add files that are not part of folders or are folder metadata files
          const filesToAdd = newFiles.filter((f) => {
            // If it's a folder metadata file, include it
            if (f.path.startsWith("folder:")) {
              return true;
            }

            // For regular files, exclude them if they might be part of a folder
            return !folderNames.some((folderName) =>
              f.path.includes(folderName)
            );
          });

          const paths = filesToAdd.map((f) => f.path);
          safeDispatch({ type: "ADD_UPLOADED_FILES", payload: paths });
          break;

        case "error":
          toast.error(data.content.message as string);
          safeDispatch({ type: "SET_IS_UPLOADING", payload: false });
          safeDispatch({ type: "SET_LOADING", payload: false });
          safeDispatch({ type: "SET_GENERATING_PROMPT", payload: false });
          break;
      }
    },
    [state.workspaceInfo, safeDispatch]
  );

  const handleClickAction = useCallback(
    debounce((data: ActionStep | undefined, showTabOnly = false) => {
      if (!data) return;

      switch (data.type) {
        case TOOL.WEB_SEARCH:
          safeDispatch({ type: "SET_ACTIVE_TAB", payload: TAB.BROWSER });
          safeDispatch({ type: "SET_CURRENT_ACTION_DATA", payload: data });
          break;

        case TOOL.IMAGE_GENERATE:
        case TOOL.IMAGE_SEARCH:
        case TOOL.BROWSER_USE:
        case TOOL.VISIT:
          safeDispatch({ type: "SET_ACTIVE_TAB", payload: TAB.BROWSER });
          safeDispatch({ type: "SET_CURRENT_ACTION_DATA", payload: data });
          break;

        case TOOL.BROWSER_CLICK:
        case TOOL.BROWSER_ENTER_TEXT:
        case TOOL.BROWSER_PRESS_KEY:
        case TOOL.BROWSER_GET_SELECT_OPTIONS:
        case TOOL.BROWSER_SELECT_DROPDOWN_OPTION:
        case TOOL.BROWSER_SWITCH_TAB:
        case TOOL.BROWSER_OPEN_NEW_TAB:
        case TOOL.BROWSER_VIEW:
        case TOOL.BROWSER_NAVIGATION:
        case TOOL.BROWSER_RESTART:
        case TOOL.BROWSER_WAIT:
        case TOOL.BROWSER_SCROLL_DOWN:
        case TOOL.BROWSER_SCROLL_UP:
          safeDispatch({ type: "SET_ACTIVE_TAB", payload: TAB.BROWSER });
          safeDispatch({ type: "SET_CURRENT_ACTION_DATA", payload: data });
          break;

        case TOOL.BASH:
          safeDispatch({ type: "SET_ACTIVE_TAB", payload: TAB.TERMINAL });
          if (!showTabOnly) {
            setTimeout(() => {
              if (!data.data?.isResult) {
                // query
                xtermRef?.current?.writeln(
                  `${data.data.tool_input?.command || ""}`
                );
              }
              // result
              if (data.data.result) {
                const lines = `${data.data.result || ""}`.split("\n");
                lines.forEach((line) => {
                  xtermRef?.current?.writeln(line);
                });
                xtermRef?.current?.write("$ ");
              }
            }, 500);
          }
          break;

        case TOOL.STR_REPLACE_EDITOR:
          safeDispatch({ type: "SET_ACTIVE_TAB", payload: TAB.CODE });
          safeDispatch({ type: "SET_CURRENT_ACTION_DATA", payload: data });
          const path = data.data.tool_input?.path || data.data.tool_input?.file;
          if (path) {
            safeDispatch({
              type: "SET_ACTIVE_FILE",
              payload: path.startsWith(state.workspaceInfo)
                ? path
                : `${state.workspaceInfo}/${path}`,
            });
          }
          break;

        default:
          break;
      }
    }, 50),
    [state.workspaceInfo, safeDispatch]
  );

  return { handleEvent, handleClickAction };
}
