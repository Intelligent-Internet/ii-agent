"use client";

import { Terminal as XTerm } from "@xterm/xterm";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import {
  Code,
  Globe,
  Terminal as TerminalIcon,
  X,
  Loader2,
  Share,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { cloneDeep, debounce } from "lodash";
import dynamic from "next/dynamic";
import { Orbitron } from "next/font/google";
import Cookies from "js-cookie";
import { v4 as uuidv4 } from "uuid";
import { useRouter, useSearchParams } from "next/navigation";
import SidebarButton from "@/components/sidebar-button";

const orbitron = Orbitron({
  subsets: ["latin"],
});

import Browser from "@/components/browser";
import CodeEditor from "@/components/code-editor";
import QuestionInput from "@/components/question-input";
import SearchBrowser from "@/components/search-browser";
const Terminal = dynamic(() => import("@/components/terminal"), {
  ssr: false,
});
import { Button } from "@/components/ui/button";
import {
  ActionStep,
  AgentEvent,
  IEvent,
  Message,
  TAB,
  TOOL,
} from "@/typings/agent";
import ChatMessage from "./chat-message";
import ImageBrowser from "./image-browser";

export default function Home() {
  const xtermRef = useRef<XTerm | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const searchParams = useSearchParams();
  const router = useRouter();

  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [activeTab, setActiveTab] = useState(TAB.BROWSER);
  const [currentActionData, setCurrentActionData] = useState<ActionStep>();
  const [activeFileCodeEditor, setActiveFileCodeEditor] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [isCompleted, setIsCompleted] = useState(false);
  const [workspaceInfo, setWorkspaceInfo] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
  const [isUseDeepResearch, setIsUseDeepResearch] = useState(false);
  const [deviceId, setDeviceId] = useState<string>("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [filesContent, setFilesContent] = useState<{ [key: string]: string }>(
    {}
  );
  const [browserUrl, setBrowserUrl] = useState("");
  const [isGeneratingPrompt, setIsGeneratingPrompt] = useState(false);

  const isReplayMode = useMemo(() => !!searchParams.get("id"), [searchParams]);

  // Get session ID from URL params
  useEffect(() => {
    const id = searchParams.get("id");
    setSessionId(id);
  }, [searchParams]);

  // Fetch session events when session ID is available
  useEffect(() => {
    const fetchSessionEvents = async () => {
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
        setWorkspaceInfo(data.events?.[0]?.workspace_dir);

        if (data.events && Array.isArray(data.events)) {
          // Process events to reconstruct the conversation
          const reconstructedMessages: Message[] = [];

          // Function to process events with delay
          const processEventsWithDelay = async () => {
            setIsLoading(true);
            for (let i = 0; i < data.events.length; i++) {
              const event = data.events[i];
              // Process each event with a 2-second delay
              await new Promise((resolve) => setTimeout(resolve, 50));
              handleEvent({ ...event.event_payload, id: event.id });
            }
            setIsLoading(false);
          };

          // Start processing events with delay
          processEventsWithDelay();

          // Set the reconstructed messages
          if (reconstructedMessages.length > 0) {
            setMessages(reconstructedMessages);
            setIsCompleted(true);
          }

          // Extract workspace info if available
          const workspaceEvent = data.events.find(
            (e: IEvent) => e.event_type === AgentEvent.WORKSPACE_INFO
          );
          if (workspaceEvent && workspaceEvent.event_payload.path) {
            setWorkspaceInfo(workspaceEvent.event_payload.path);
          }
        }
      } catch (error) {
        console.error("Failed to fetch session events:", error);
        toast.error("Failed to load session history");
      } finally {
        setIsLoadingSession(false);
      }
    };

    fetchSessionEvents();
  }, [searchParams]);

  // Initialize device ID on page load
  useEffect(() => {
    // Check if device ID exists in cookies
    let existingDeviceId = Cookies.get("device_id");

    // If no device ID exists, generate a new one and save it
    if (!existingDeviceId) {
      existingDeviceId = uuidv4();

      // Set cookie with a long expiration (1 year)
      Cookies.set("device_id", existingDeviceId, {
        expires: 365,
        sameSite: "strict",
        secure: window.location.protocol === "https:",
      });

      console.log("Generated new device ID:", existingDeviceId);
    } else {
      console.log("Using existing device ID:", existingDeviceId);
    }

    // Set the device ID in state
    setDeviceId(existingDeviceId);
  }, []);

  const handleEnhancePrompt = () => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      toast.error("WebSocket connection is not open. Please try again.");
      return;
    }
    setIsGeneratingPrompt(true);
    socket.send(
      JSON.stringify({
        type: "enhance_prompt",
        content: {
          text: currentQuestion,
          files: uploadedFiles?.map((file) => `.${file}`),
        },
      })
    );
  };

  const handleClickAction = debounce(
    (data: ActionStep | undefined, showTabOnly = false) => {
      if (!data) return;

      switch (data.type) {
        case TOOL.WEB_SEARCH:
          setActiveTab(TAB.BROWSER);
          setCurrentActionData(data);
          break;

        case TOOL.IMAGE_GENERATE:
        case TOOL.BROWSER_USE:
        case TOOL.VISIT:
          setActiveTab(TAB.BROWSER);
          setCurrentActionData(data);
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
          setActiveTab(TAB.BROWSER);
          setCurrentActionData(data);
          break;

        case TOOL.BASH:
          setActiveTab(TAB.TERMINAL);
          if (!showTabOnly) {
            setTimeout(() => {
              if (!data.data?.isResult) {
                // query
                xtermRef.current?.writeln(
                  `${data.data.tool_input?.command || ""}`
                );
              }
              // result
              if (data.data.result) {
                const lines = `${data.data.result || ""}`.split("\n");
                lines.forEach((line) => {
                  xtermRef.current?.writeln(line);
                });
                xtermRef.current?.write("$ ");
              }
            }, 500);
          }
          break;

        case TOOL.STR_REPLACE_EDITOR:
          setActiveTab(TAB.CODE);
          setCurrentActionData(data);
          const path = data.data.tool_input?.path || data.data.tool_input?.file;
          if (path) {
            setActiveFileCodeEditor(
              path.startsWith(workspaceInfo) ? path : `${workspaceInfo}/${path}`
            );
          }
          break;

        default:
          break;
      }
    },
    50
  );

  const handleQuestionSubmit = async (newQuestion: string) => {
    if (!newQuestion.trim() || isLoading) return;

    setIsLoading(true);
    setCurrentQuestion("");
    setIsCompleted(false);

    if (!sessionId) {
      const id = `${workspaceInfo}`.split("/").pop();
      if (id) {
        setSessionId(id);
      }
    }

    const newUserMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: newQuestion,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, newUserMessage]);

    if (!socket || socket.readyState !== WebSocket.OPEN) {
      toast.error("WebSocket connection is not open. Please try again.");
      setIsLoading(false);
      return;
    }

    // send init agent event when first query
    if (!sessionId) {
      socket.send(
        JSON.stringify({
          type: "init_agent",
          content: {
            tool_args: {
              deep_research: isUseDeepResearch,
              pdf: true,
              media_generation: true,
              audio_generation: true,
              browser: true,
            },
          },
        })
      );
    }

    // Send the query using the existing socket connection
    socket.send(
      JSON.stringify({
        type: "query",
        content: {
          text: newQuestion,
          resume: messages.length > 0,
          files: uploadedFiles?.map((file) => `.${file}`),
        },
      })
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleQuestionSubmit((e.target as HTMLTextAreaElement).value);
    }
  };

  const resetChat = () => {
    if (socket) {
      socket.close();
    }
    setSessionId(null);
    router.push("/");
    setMessages([]);
    setIsLoading(false);
    setIsCompleted(false);
  };

  const handleOpenVSCode = () => {
    let url = process.env.NEXT_PUBLIC_VSCODE_URL || "http://127.0.0.1:8080";
    url += `/?folder=${workspaceInfo}`;
    window.open(url, "_blank");
  };

  const parseJson = (jsonString: string) => {
    try {
      return JSON.parse(jsonString);
    } catch {
      return null;
    }
  };

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    if (!event.target.files || event.target.files.length === 0) return;

    const files = Array.from(event.target.files);

    // Create a map to track upload status for each file
    const fileStatusMap: { [filename: string]: boolean } = {};
    files.forEach((file) => {
      fileStatusMap[file.name] = false; // false = not uploaded yet
    });

    setIsUploading(true);

    // Create a map of filename to content for message history
    const fileContentMap: { [filename: string]: string } = {};

    // Get the connection ID from the workspace path
    const workspacePath = workspaceInfo || "";
    const connectionId = workspacePath.split("/").pop();

    // Add files to message history (initially without content)
    const newUserMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      files: files.map((file) => file.name),
      fileContents: fileContentMap,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, newUserMessage]);

    // Process each file in parallel
    const uploadPromises = files.map(async (file) => {
      return new Promise<{ name: string; success: boolean }>(
        async (resolve) => {
          try {
            const reader = new FileReader();

            reader.onload = async (e) => {
              const content = e.target?.result as string;
              fileContentMap[file.name] = content;

              // Upload the file
              const response = await fetch(
                `${process.env.NEXT_PUBLIC_API_URL}/api/upload`,
                {
                  method: "POST",
                  headers: {
                    "Content-Type": "application/json",
                  },
                  body: JSON.stringify({
                    session_id: connectionId,
                    file: {
                      path: file.name,
                      content,
                    },
                  }),
                }
              );

              const result = await response.json();

              if (response.ok) {
                // Update uploaded files state
                setUploadedFiles((prev) => [...prev, result.file.path]);
                resolve({ name: file.name, success: true });
              } else {
                console.error(`Error uploading ${file.name}:`, result.error);
                resolve({ name: file.name, success: false });
              }
            };

            reader.onerror = () => {
              resolve({ name: file.name, success: false });
            };

            // Read as data URL
            reader.readAsDataURL(file);
          } catch (error) {
            console.error(`Error processing ${file.name}:`, error);
            resolve({ name: file.name, success: false });
          }
        }
      );
    });

    try {
      // Wait for all uploads to complete
      const results = await Promise.all(uploadPromises);

      // Check if any uploads failed
      const failedUploads = results.filter((r) => !r.success);
      if (failedUploads.length > 0) {
        toast.error(`Failed to upload ${failedUploads.length} file(s)`);
      }

      // Update message with final content
      setMessages((prev) => {
        const updatedMessages = [...prev];
        const messageIndex = updatedMessages.findIndex(
          (m) => m.id === newUserMessage.id
        );
        if (messageIndex >= 0) {
          updatedMessages[messageIndex] = {
            ...updatedMessages[messageIndex],
            fileContents: fileContentMap,
          };
        }
        return updatedMessages;
      });
    } catch (error) {
      console.error("Error uploading files:", error);
      toast.error("Error uploading files");
    } finally {
      setIsUploading(false);
      // Clear the input
      event.target.value = "";
    }
  };

  const getRemoteURL = (path: string | undefined) => {
    const workspaceId = workspaceInfo.split("/").pop();
    return `${process.env.NEXT_PUBLIC_API_URL}/workspace/${workspaceId}/${path}`;
  };

  const handleEvent = (data: {
    id: string;
    type: AgentEvent;
    content: Record<string, unknown>;
  }) => {
    switch (data.type) {
      case AgentEvent.USER_MESSAGE:
        setMessages((prev) => [
          ...prev,
          {
            id: data.id,
            role: "user",
            content: data.content.text as string,
            timestamp: Date.now(),
          },
        ]);

        break;
      case AgentEvent.PROMPT_GENERATED:
        setIsGeneratingPrompt(false);
        setCurrentQuestion(data.content.result as string);
        break;
      case AgentEvent.PROCESSING:
        setIsLoading(true);
        break;
      case AgentEvent.WORKSPACE_INFO:
        setWorkspaceInfo(data.content.path as string);
        break;
      case AgentEvent.AGENT_THINKING:
        setMessages((prev) => [
          ...prev,
          {
            id: data.id,
            role: "assistant",
            content: data.content.text as string,
            timestamp: Date.now(),
          },
        ]);
        break;

      case AgentEvent.TOOL_CALL:
        if (data.content.tool_name === TOOL.SEQUENTIAL_THINKING) {
          setMessages((prev) => [
            ...prev,
            {
              id: data.id,
              role: "assistant",
              content: (data.content.tool_input as { thought: string })
                .thought as string,
              timestamp: Date.now(),
            },
          ]);
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
            setBrowserUrl(url);
          }
          setMessages((prev) => [...prev, message]);
          handleClickAction(message.action);
        }
        break;

      case AgentEvent.FILE_EDIT:
        setMessages((prev) => {
          const lastMessage = cloneDeep(prev[prev.length - 1]);
          if (
            lastMessage.action &&
            lastMessage.action.type === TOOL.STR_REPLACE_EDITOR
          ) {
            lastMessage.action.data.content = data.content.content as string;
            lastMessage.action.data.path = data.content.path as string;
            const filePath = (data.content.path as string)?.includes(
              workspaceInfo
            )
              ? (data.content.path as string)
              : `${workspaceInfo}/${data.content.path}`;

            setFilesContent((prev) => {
              return {
                ...prev,
                [filePath]: data.content.content as string,
              };
            });
          }
          setTimeout(() => {
            handleClickAction(lastMessage.action);
          }, 500);
          return [...prev.slice(0, -1), lastMessage];
        });
        break;

      case AgentEvent.BROWSER_USE:
        // const message: Message = {
        //   id: data.id,
        //   role: "assistant",
        //   action: {
        //     type: data.type as unknown as TOOL,
        //     data: {
        //       result: data.content.screenshot as string,
        //       tool_input: {
        //         url: data.content.url as string,
        //       },
        //     },
        //   },
        //   timestamp: Date.now(),
        // };
        // setMessages((prev) => [...prev, message]);
        // handleClickAction(message.action);
        break;

      case AgentEvent.TOOL_RESULT:
        if (data.content.tool_name === TOOL.BROWSER_USE) {
          setMessages((prev) => [
            ...prev,
            {
              id: data.id,
              role: "assistant",
              content: data.content.result as string,
              timestamp: Date.now(),
            },
          ]);
        } else {
          if (
            data.content.tool_name !== TOOL.SEQUENTIAL_THINKING &&
            data.content.tool_name !== TOOL.PRESENTATION
          ) {
            // TODO: Implement helper function to handle tool results
            setMessages((prev) => {
              const lastMessage = cloneDeep(prev[prev.length - 1]);
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
                setTimeout(() => {
                  handleClickAction(lastMessage.action);
                }, 500);
                return [...prev.slice(0, -1), lastMessage];
              } else {
                return [
                  ...prev,
                  { ...lastMessage, action: data.content as ActionStep },
                ];
              }
            });
          }
        }

        break;

      case AgentEvent.AGENT_RESPONSE:
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now().toString(),
            role: "assistant",
            content: data.content.text as string,
            timestamp: Date.now(),
          },
        ]);
        setIsCompleted(true);
        setIsLoading(false);
        break;

      case AgentEvent.UPLOAD_SUCCESS:
        setIsUploading(false);

        // Update the uploaded files state
        const newFiles = data.content.files as {
          path: string;
          saved_path: string;
        }[];
        const paths = newFiles.map((f) => f.path);
        setUploadedFiles((prev) => [...prev, ...paths]);

        break;

      case "error":
        toast.error(data.content.message as string);
        setIsUploading(false);
        setIsLoading(false);
        break;
    }
  };

  const isInChatView = useMemo(
    () => !!sessionId && !isLoadingSession,
    [isLoadingSession, sessionId]
  );

  const handleShare = () => {
    if (!sessionId) return;
    const url = `${window.location.origin}/?id=${sessionId}`;
    navigator.clipboard.writeText(url);
    toast.success("Copied to clipboard");
  };

  useEffect(() => {
    // Connect to WebSocket when the component mounts
    const connectWebSocket = () => {
      const params = new URLSearchParams({ device_id: deviceId });
      const ws = new WebSocket(
        `${process.env.NEXT_PUBLIC_API_URL}/ws?${params.toString()}`
      );

      ws.onopen = () => {
        console.log("WebSocket connection established");
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
        toast.error("WebSocket connection error");
      };

      ws.onclose = () => {
        console.log("WebSocket connection closed");
        setSocket(null);
      };

      setSocket(ws);
    };

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

  const isBrowserTool = useMemo(
    () =>
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
      ].includes(currentActionData?.type as TOOL),
    [currentActionData]
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages?.length]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#191E1B]">
      <SidebarButton />
      {!isInChatView && (
        <Image
          src="/logo-only.png"
          alt="II-Agent Logo"
          width={80}
          height={80}
          className="rounded-sm"
        />
      )}
      <div
        className={`flex justify-between w-full ${
          !isInChatView ? "pt-0 pb-8" : "p-4"
        }`}
      >
        {!isInChatView && <div />}
        <motion.h1
          className={`font-semibold text-center ${
            isInChatView ? "flex items-center gap-x-2 text-2xl" : "text-4xl"
          } ${orbitron.className}`}
          layout
          layoutId="page-title"
        >
          {isInChatView && (
            <Image
              src="/logo-only.png"
              alt="II-Agent Logo"
              width={40}
              height={40}
              className="rounded-sm"
            />
          )}
          {`II-Agent`}
        </motion.h1>
        {isInChatView ? (
          <div className="flex gap-x-2">
            <Button
              className="cursor-pointer h-10"
              variant="outline"
              onClick={handleShare}
            >
              <Share /> Share
            </Button>
            <Button className="cursor-pointer" onClick={resetChat}>
              <X className="size-5" />
            </Button>
          </div>
        ) : (
          <div />
        )}
      </div>
      {isLoadingSession ? (
        <div className="flex flex-col items-center justify-center p-8">
          <Loader2 className="h-8 w-8 text-white animate-spin mb-4" />
          <p className="text-white text-lg">Loading session history...</p>
        </div>
      ) : (
        <LayoutGroup>
          <AnimatePresence mode="wait">
            {!isInChatView ? (
              <QuestionInput
                placeholder="Give II-Agent a task to work on..."
                value={currentQuestion}
                setValue={setCurrentQuestion}
                handleKeyDown={handleKeyDown}
                handleSubmit={handleQuestionSubmit}
                handleFileUpload={handleFileUpload}
                isUploading={isUploading}
                isUseDeepResearch={isUseDeepResearch}
                setIsUseDeepResearch={setIsUseDeepResearch}
                isDisabled={!socket || socket.readyState !== WebSocket.OPEN}
                isGeneratingPrompt={isGeneratingPrompt}
                handleEnhancePrompt={handleEnhancePrompt}
              />
            ) : (
              <motion.div
                key="chat-view"
                initial={{ opacity: 0, y: 30, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -20, scale: 0.95 }}
                transition={{
                  type: "spring",
                  stiffness: 300,
                  damping: 30,
                  mass: 1,
                }}
                className="w-full grid grid-cols-10 write-report overflow-hidden flex-1 pr-4 pb-4 "
              >
                <ChatMessage
                  messages={messages}
                  isLoading={isLoading}
                  isCompleted={isCompleted}
                  workspaceInfo={workspaceInfo}
                  handleClickAction={handleClickAction}
                  isUploading={isUploading}
                  isUseDeepResearch={isUseDeepResearch}
                  isReplayMode={isReplayMode}
                  currentQuestion={currentQuestion}
                  messagesEndRef={messagesEndRef}
                  setCurrentQuestion={setCurrentQuestion}
                  handleKeyDown={handleKeyDown}
                  handleQuestionSubmit={handleQuestionSubmit}
                  handleFileUpload={handleFileUpload}
                  isGeneratingPrompt={isGeneratingPrompt}
                  handleEnhancePrompt={handleEnhancePrompt}
                />

                <div className="col-span-6 bg-[#1e1f23] border border-[#3A3B3F] p-4 rounded-2xl">
                  <div className="pb-4 bg-neutral-850 flex items-center justify-between">
                    <div className="flex gap-x-4">
                      <Button
                        className={`cursor-pointer hover:!bg-black ${
                          activeTab === TAB.BROWSER
                            ? "bg-gradient-skyblue-lavender !text-black"
                            : ""
                        }`}
                        variant="outline"
                        onClick={() => setActiveTab(TAB.BROWSER)}
                      >
                        <Globe className="size-4" /> Browser
                      </Button>
                      <Button
                        className={`cursor-pointer hover:!bg-black ${
                          activeTab === TAB.CODE
                            ? "bg-gradient-skyblue-lavender !text-black"
                            : ""
                        }`}
                        variant="outline"
                        onClick={() => setActiveTab(TAB.CODE)}
                      >
                        <Code className="size-4" /> Code
                      </Button>
                      <Button
                        className={`cursor-pointer hover:!bg-black ${
                          activeTab === TAB.TERMINAL
                            ? "bg-gradient-skyblue-lavender !text-black"
                            : ""
                        }`}
                        variant="outline"
                        onClick={() => setActiveTab(TAB.TERMINAL)}
                      >
                        <TerminalIcon className="size-4" /> Terminal
                      </Button>
                    </div>
                    <Button
                      className="cursor-pointer"
                      variant="outline"
                      onClick={handleOpenVSCode}
                    >
                      <Image
                        src={"/vscode.png"}
                        alt="VS Code"
                        width={20}
                        height={20}
                      />{" "}
                      Open with VS Code
                    </Button>
                  </div>
                  <Browser
                    className={
                      activeTab === TAB.BROWSER &&
                      (currentActionData?.type === TOOL.VISIT || isBrowserTool)
                        ? ""
                        : "hidden"
                    }
                    url={currentActionData?.data?.tool_input?.url || browserUrl}
                    screenshot={
                      isBrowserTool
                        ? (currentActionData?.data.result as string)
                        : undefined
                    }
                    raw={
                      currentActionData?.type === TOOL.VISIT
                        ? (currentActionData?.data?.result as string)
                        : undefined
                    }
                  />
                  <SearchBrowser
                    className={
                      activeTab === TAB.BROWSER &&
                      currentActionData?.type === TOOL.WEB_SEARCH
                        ? ""
                        : "hidden"
                    }
                    keyword={currentActionData?.data.tool_input?.query}
                    search_results={
                      currentActionData?.type === TOOL.WEB_SEARCH &&
                      currentActionData?.data?.result
                        ? parseJson(currentActionData?.data?.result as string)
                        : undefined
                    }
                  />
                  <ImageBrowser
                    className={
                      activeTab === TAB.BROWSER &&
                      currentActionData?.type === TOOL.IMAGE_GENERATE
                        ? ""
                        : "hidden"
                    }
                    url={currentActionData?.data.tool_input?.output_filename}
                    image={getRemoteURL(
                      currentActionData?.data.tool_input?.output_filename
                    )}
                  />
                  <CodeEditor
                    currentActionData={currentActionData}
                    activeTab={activeTab}
                    className={activeTab === TAB.CODE ? "" : "hidden"}
                    workspaceInfo={workspaceInfo}
                    activeFile={activeFileCodeEditor}
                    setActiveFile={setActiveFileCodeEditor}
                    filesContent={filesContent}
                    isReplayMode={isReplayMode}
                  />
                  <Terminal
                    ref={xtermRef}
                    className={activeTab === TAB.TERMINAL ? "" : "hidden"}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </LayoutGroup>
      )}
    </div>
  );
}
