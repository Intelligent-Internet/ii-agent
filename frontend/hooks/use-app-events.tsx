"use client";

import { RefObject } from "react";
import { cloneDeep, debounce } from "lodash";
import { toast } from "sonner";

import { useAppContext } from "@/context/app-context";
import { AgentEvent, TOOL, ActionStep, Message, TAB } from "@/typings/agent";
import { Terminal as XTerm } from "@xterm/xterm";

export function useAppEvents({
  xtermRef,
}: {
  xtermRef: RefObject<XTerm | null>;
}) {
  const { state, dispatch } = useAppContext();

  const handleEvent = (
    data: {
      id: string;
      type: AgentEvent;
      content: Record<string, unknown>;
    },
    workspacePath?: string
  ) => {
    switch (data.type) {
      case AgentEvent.USER_MESSAGE:
        dispatch({
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
        dispatch({ type: "SET_GENERATING_PROMPT", payload: false });
        dispatch({
          type: "SET_CURRENT_QUESTION",
          payload: data.content.result as string,
        });
        break;

      case AgentEvent.PROCESSING:
        dispatch({ type: "SET_LOADING", payload: true });
        break;

      case AgentEvent.WORKSPACE_INFO:
        dispatch({
          type: "SET_WORKSPACE_INFO",
          payload: data.content.path as string,
        });
        break;

      case AgentEvent.AGENT_THINKING:
        dispatch({
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
          dispatch({
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
          dispatch({
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
            dispatch({ type: "SET_BROWSER_URL", payload: url });
          }
          dispatch({ type: "ADD_MESSAGE", payload: message });
          handleClickAction(message.action);
        }
        break;

      case AgentEvent.FILE_EDIT:
        const messages = [...state.messages];
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

          dispatch({
            type: "ADD_FILE_CONTENT",
            payload: {
              path: filePath,
              content: data.content.content as string,
            },
          });

          setTimeout(() => {
            handleClickAction(lastMessage.action);
          }, 500);

          dispatch({
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
          dispatch({
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
            const messages = [...state.messages];
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
                    ? data.content.result.find((item) => item.type === "image")
                        ?.source?.data
                    : undefined;
              }
              lastMessage.action.data.isResult = true;
              setTimeout(() => {
                handleClickAction(lastMessage.action);
              }, 500);

              dispatch({
                type: "UPDATE_MESSAGE",
                payload: lastMessage,
              });
            } else {
              dispatch({
                type: "ADD_MESSAGE",
                payload: { ...lastMessage, action: data.content as ActionStep },
              });
            }
          }
        }
        break;

      case AgentEvent.AGENT_RESPONSE:
        dispatch({
          type: "ADD_MESSAGE",
          payload: {
            id: Date.now().toString(),
            role: "assistant",
            content: data.content.text as string,
            timestamp: Date.now(),
          },
        });
        dispatch({ type: "SET_COMPLETED", payload: true });
        dispatch({ type: "SET_LOADING", payload: false });
        break;

      case AgentEvent.UPLOAD_SUCCESS:
        dispatch({ type: "SET_IS_UPLOADING", payload: false });

        // Update the uploaded files state
        const newFiles = data.content.files as {
          path: string;
          saved_path: string;
        }[];
        const paths = newFiles.map((f) => f.path);
        dispatch({ type: "ADD_UPLOADED_FILES", payload: paths });
        break;

      case "error":
        toast.error(data.content.message as string);
        dispatch({ type: "SET_IS_UPLOADING", payload: false });
        dispatch({ type: "SET_LOADING", payload: false });
        dispatch({ type: "SET_GENERATING_PROMPT", payload: false });
        break;
    }
  };

  const handleClickAction = debounce(
    (data: ActionStep | undefined, showTabOnly = false) => {
      if (!data) return;

      switch (data.type) {
        case TOOL.WEB_SEARCH:
          dispatch({ type: "SET_ACTIVE_TAB", payload: TAB.BROWSER });
          dispatch({ type: "SET_CURRENT_ACTION_DATA", payload: data });
          break;

        case TOOL.IMAGE_GENERATE:
        case TOOL.IMAGE_SEARCH:
        case TOOL.BROWSER_USE:
        case TOOL.VISIT:
          dispatch({ type: "SET_ACTIVE_TAB", payload: TAB.BROWSER });
          dispatch({ type: "SET_CURRENT_ACTION_DATA", payload: data });
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
          dispatch({ type: "SET_ACTIVE_TAB", payload: TAB.BROWSER });
          dispatch({ type: "SET_CURRENT_ACTION_DATA", payload: data });
          break;

        case TOOL.BASH:
          dispatch({ type: "SET_ACTIVE_TAB", payload: TAB.TERMINAL });
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
          dispatch({ type: "SET_ACTIVE_TAB", payload: TAB.CODE });
          dispatch({ type: "SET_CURRENT_ACTION_DATA", payload: data });
          const path = data.data.tool_input?.path || data.data.tool_input?.file;
          if (path) {
            dispatch({
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
    },
    50
  );

  return { handleEvent, handleClickAction };
}
