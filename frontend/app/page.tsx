"use client";

import { Terminal as XTerm } from "@xterm/xterm";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { Check, Code, Globe, Terminal as TerminalIcon, X } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { cloneDeep, debounce } from "lodash";
import dynamic from "next/dynamic";

import Browser from "@/components/browser";
import CodeEditor from "@/components/code-editor";
import QuestionInput from "@/components/question-input";
import SearchBrowser from "@/components/search-browser";
const Terminal = dynamic(() => import("@/components/terminal"), {
  ssr: false,
});
import { Button } from "@/components/ui/button";
import { ActionStep, AgentEvent, TOOL } from "@/typings/agent";
import Action from "@/components/action";
import Markdown from "@/components/markdown";
import { getFileIconAndColor } from "@/utils/file-utils";

enum TAB {
  BROWSER = "browser",
  CODE = "code",
  TERMINAL = "terminal",
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content?: string;
  timestamp: number;
  action?: ActionStep;
  files?: string[]; // File names
  fileContents?: { [filename: string]: string }; // Base64 content of files
}

export default function Home() {
  const xtermRef = useRef<XTerm | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isInChatView, setIsInChatView] = useState(false);
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [activeTab, setActiveTab] = useState(TAB.BROWSER);
  const [currentActionData, setCurrentActionData] = useState<ActionStep>();
  const [activeFileCodeEditor, setActiveFileCodeEditor] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [isCompleted, setIsCompleted] = useState(false);
  const [workspaceInfo, setWorkspaceInfo] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);

  const handleClickAction = debounce(
    (data: ActionStep | undefined, showTabOnly = false) => {
      if (!data) return;

      setActiveFileCodeEditor("");

      switch (data.type) {
        case TOOL.TAVILY_SEARCH:
          setActiveTab(TAB.BROWSER);
          setCurrentActionData(data);
          break;

        case TOOL.BROWSER_USE:
        case TOOL.TAVILY_VISIT:
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

        case TOOL.FILE_WRITE:
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
    setIsInChatView(true);
    setCurrentQuestion("");
    setIsCompleted(false);

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

    // Create a modified question that includes information about uploaded files if needed
    let finalQuestion = newQuestion;

    // If files have been uploaded, add a note to the question with file names
    if (uploadedFiles.length > 0) {
      finalQuestion = `${newQuestion}\n\nNote: I've already uploaded the following files that you can use:\n${uploadedFiles
        .map((file) => `- ${file}`)
        .join("\n")}`;
    }

    // If files have been uploaded, add a note to the question with file names
    if (uploadedFiles.length > 0) {
      finalQuestion = `${newQuestion}\n\nNote: I've already uploaded the following files that you can use:\n${uploadedFiles
        .map((file) => `- ${file}`)
        .join("\n")}`;
    }

    // Send the query using the existing socket connection
    socket.send(
      JSON.stringify({
        type: "query",
        content: {
          text: finalQuestion,
          resume: messages.length > 0,
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
    setIsInChatView(false);
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
    const filePromises = files.map((file) => {
      return new Promise<{ name: string; content: string }>((resolve) => {
        const reader = new FileReader();

        reader.onload = (e) => {
          const result = e.target?.result;
          resolve({
            name: file.name,
            content: result as string,
          });
        };

        // Read as data URL for all files
        reader.readAsDataURL(file);
      });
    });

    try {
      setIsUploading(true);
      const fileContents = await Promise.all(filePromises);

      // Create a map of filename to content
      const fileContentMap: { [filename: string]: string } = {};
      fileContents.forEach(({ name, content }) => {
        fileContentMap[name] = content;
      });

      // Add files to message history
      const newUserMessage: Message = {
        id: Date.now().toString(),
        role: "user",
        files: files.map((file) => file.name),
        fileContents: fileContentMap,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, newUserMessage]);

      if (!socket || socket.readyState !== WebSocket.OPEN) {
        toast.error("WebSocket connection is not open. Please try again.");
        setIsUploading(false);
        return;
      }

      socket.send(
        JSON.stringify({
          type: "upload_file",
          content: {
            files: fileContents.map(({ name, content }) => ({
              path: name,
              content,
            })),
          },
        })
      );

      // Clear the input
      event.target.value = "";
    } catch (error) {
      console.error("Error uploading files:", error);
      toast.error("Error uploading files");
      setIsUploading(false);
    }
  };

  useEffect(() => {
    // Connect to WebSocket when the component mounts
    const connectWebSocket = () => {
      const ws = new WebSocket(`${process.env.NEXT_PUBLIC_API_URL}/ws`);

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

          switch (data.type) {
            case AgentEvent.PROCESSING:
              setIsLoading(true);
              break;
            case AgentEvent.WORKSPACE_INFO:
              setWorkspaceInfo(data.content.path);
              break;
            case AgentEvent.AGENT_THINKING:
              setMessages((prev) => [
                ...prev,
                {
                  id: Date.now().toString(),
                  role: "assistant",
                  content: data.content.text,
                  timestamp: Date.now(),
                },
              ]);
              break;

            case AgentEvent.TOOL_CALL:
              if (data.content.tool_name === TOOL.SEQUENTIAL_THINKING) {
                setMessages((prev) => [
                  ...prev,
                  {
                    id: Date.now().toString(),
                    role: "assistant",
                    content: data.content.tool_input.thought,
                    timestamp: Date.now(),
                  },
                ]);
              } else {
                const message: Message = {
                  id: Date.now().toString(),
                  role: "assistant",
                  action: {
                    type: data.content.tool_name,
                    data: data.content,
                  },
                  timestamp: Date.now(),
                };
                setMessages((prev) => [...prev, message]);
                handleClickAction(message.action);
              }
              break;

            case AgentEvent.BROWSER_USE:
              const message: Message = {
                id: Date.now().toString(),
                role: "assistant",
                action: {
                  type: data.type,
                  data: {
                    result: data.content.screenshot,
                    tool_input: {
                      url: data.content.url,
                    },
                  },
                },
                timestamp: Date.now(),
              };
              setMessages((prev) => [...prev, message]);
              handleClickAction(message.action);
              break;

            case AgentEvent.TOOL_RESULT:
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
                ].includes(data.content.tool_name)
              ) {
                break;
              }
              if (data.content.tool_name === TOOL.BROWSER_USE) {
                setMessages((prev) => [
                  ...prev,
                  {
                    id: Date.now().toString(),
                    role: "assistant",
                    content: data.content.result,
                    timestamp: Date.now(),
                  },
                ]);
              } else {
                if (data.content.tool_name !== TOOL.SEQUENTIAL_THINKING) {
                  setMessages((prev) => {
                    const lastMessage = cloneDeep(prev[prev.length - 1]);
                    if (
                      lastMessage.action &&
                      lastMessage.action?.type === data.content.tool_name
                    ) {
                      lastMessage.id = Date.now().toString();
                      lastMessage.action.data.result = data.content.result;
                      lastMessage.action.data.isResult = true;
                      setTimeout(() => {
                        handleClickAction(lastMessage.action);
                      }, 500);
                      return [...prev.slice(0, -1), lastMessage];
                    } else {
                      return [
                        ...prev,
                        { ...lastMessage, action: data.content },
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
                  content: data.content.text,
                  timestamp: Date.now(),
                },
              ]);
              setIsCompleted(true);
              setIsLoading(false);
              break;

            case AgentEvent.UPLOAD_SUCCESS:
              setIsUploading(false);

              // Update the uploaded files state
              const newFiles = data.content.files.map(
                (f: { path: string; saved_path: string }) => f.path
              );
              setUploadedFiles((prev) => [...prev, ...newFiles]);

              break;

            case "error":
              toast.error(data.content.message);
              setIsUploading(false);
              setIsLoading(false);
              break;
          }
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

    connectWebSocket();

    // Clean up the WebSocket connection when the component unmounts
    return () => {
      if (socket) {
        socket.close();
      }
    };
  }, []); // Empty dependency array means this effect runs once on mount

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages?.length]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-slate-850">
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
          }`}
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
          <Button className="cursor-pointer" onClick={resetChat}>
            <X className="size-5" />
          </Button>
        ) : (
          <div />
        )}
      </div>

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
              <div className="col-span-4">
                <motion.div
                  className="p-4 pt-0 w-full h-full max-h-[calc(100vh-230px)] overflow-y-auto relative"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2, duration: 0.3 }}
                >
                  {messages.map((message, index) => (
                    <motion.div
                      key={message.id}
                      className={`mb-4 ${
                        message.role === "user" ? "text-right" : "text-left"
                      }`}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.1 * index, duration: 0.3 }}
                    >
                      {message.files && message.files.length > 0 && (
                        <div className="flex flex-col gap-2 mb-2">
                          {message.files.map((fileName, fileIndex) => {
                            // Check if the file is an image
                            const isImage =
                              fileName.match(/\.(jpeg|jpg|gif|png|webp)$/i) !==
                              null;

                            if (
                              isImage &&
                              message.fileContents &&
                              message.fileContents[fileName]
                            ) {
                              return (
                                <div
                                  key={`${message.id}-file-${fileIndex}`}
                                  className="inline-block ml-auto rounded-3xl overflow-hidden max-w-[320px]"
                                >
                                  <div className="w-40 h-40 rounded-xl overflow-hidden">
                                    <img
                                      src={message.fileContents[fileName]}
                                      alt={fileName}
                                      className="w-full h-full object-cover"
                                    />
                                  </div>
                                </div>
                              );
                            }

                            // For non-image files, use the existing code
                            const { IconComponent, bgColor, label } =
                              getFileIconAndColor(fileName);

                            return (
                              <div
                                key={`${message.id}-file-${fileIndex}`}
                                className="inline-block ml-auto bg-[#35363a] text-white rounded-2xl px-4 py-3 border border-gray-700 shadow-sm"
                              >
                                <div className="flex items-center gap-3">
                                  <div
                                    className={`flex items-center justify-center w-12 h-12 ${bgColor} rounded-xl`}
                                  >
                                    <IconComponent className="size-6 text-white" />
                                  </div>
                                  <div className="flex flex-col">
                                    <span className="text-base font-medium">
                                      {fileName}
                                    </span>
                                    <span className="text-left text-sm text-gray-500">
                                      {label}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {message.content && (
                        <motion.div
                          className={`inline-block text-left rounded-lg ${
                            message.role === "user"
                              ? "bg-[#35363a] p-3 text-white max-w-[80%] border border-[#3A3B3F] shadow-sm"
                              : "text-white"
                          }`}
                          initial={{ scale: 0.9 }}
                          animate={{ scale: 1 }}
                          transition={{
                            type: "spring",
                            stiffness: 500,
                            damping: 30,
                          }}
                        >
                          {message.role === "user" ? (
                            message.content
                          ) : (
                            <Markdown>{message.content}</Markdown>
                          )}
                        </motion.div>
                      )}

                      {message.action && (
                        <motion.div
                          className="mt-2"
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: 0.1 * index, duration: 0.3 }}
                        >
                          <Action
                            workspaceInfo={workspaceInfo}
                            type={message.action.type}
                            value={message.action.data}
                            onClick={() =>
                              handleClickAction(message.action, true)
                            }
                          />
                        </motion.div>
                      )}
                    </motion.div>
                  ))}

                  {isLoading && (
                    <motion.div
                      className="mb-4 text-left"
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        type: "spring",
                        stiffness: 300,
                        damping: 30,
                      }}
                    >
                      <motion.div
                        className="inline-block p-3 text-left rounded-lg bg-neutral-800/90 text-white backdrop-blur-sm"
                        initial={{ scale: 0.95 }}
                        animate={{ scale: 1 }}
                        transition={{
                          type: "spring",
                          stiffness: 400,
                          damping: 25,
                        }}
                      >
                        <div className="flex items-center gap-3">
                          <div className="flex space-x-2">
                            <div className="w-2 h-2 bg-white rounded-full animate-[dot-bounce_1.2s_ease-in-out_infinite_0ms]" />
                            <div className="w-2 h-2 bg-white rounded-full animate-[dot-bounce_1.2s_ease-in-out_infinite_200ms]" />
                            <div className="w-2 h-2 bg-white rounded-full animate-[dot-bounce_1.2s_ease-in-out_infinite_400ms]" />
                          </div>
                        </div>
                      </motion.div>
                    </motion.div>
                  )}

                  {isCompleted && (
                    <div className="flex gap-x-2 items-center bg-[#25BA3B1E] text-green-600 text-sm p-2 rounded-full">
                      <Check className="size-4" />
                      <span>II-Agent has completed the current task.</span>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </motion.div>
                <motion.div
                  className="sticky bottom-0 left-0 w-full"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2, duration: 0.3 }}
                >
                  <QuestionInput
                    className="p-4 pb-0 w-full max-w-none"
                    textareaClassName="h-30 w-full"
                    placeholder="Ask me anything..."
                    value={currentQuestion}
                    setValue={setCurrentQuestion}
                    handleKeyDown={handleKeyDown}
                    handleSubmit={handleQuestionSubmit}
                    handleFileUpload={handleFileUpload}
                    isUploading={isUploading}
                  />
                </motion.div>
              </div>

              <motion.div className="col-span-6 bg-[#1e1f23] border border-[#3A3B3F] p-4 rounded-2xl">
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
                    (currentActionData?.type === TOOL.TAVILY_VISIT ||
                      currentActionData?.type === TOOL.BROWSER_USE)
                      ? ""
                      : "hidden"
                  }
                  url={currentActionData?.data?.tool_input?.url}
                  screenshot={
                    currentActionData?.type === TOOL.BROWSER_USE
                      ? (currentActionData?.data.result as string)
                      : undefined
                  }
                  raw={
                    currentActionData?.type === TOOL.TAVILY_VISIT
                      ? parseJson(currentActionData?.data?.result as string)
                          ?.raw_content
                      : undefined
                  }
                />
                <SearchBrowser
                  className={
                    activeTab === TAB.BROWSER &&
                    currentActionData?.type === TOOL.TAVILY_SEARCH
                      ? ""
                      : "hidden"
                  }
                  keyword={currentActionData?.data.tool_input?.query}
                  search_results={
                    currentActionData?.type === TOOL.TAVILY_SEARCH &&
                    currentActionData?.data?.result
                      ? parseJson(currentActionData?.data?.result as string)
                      : undefined
                  }
                />
                <CodeEditor
                  key={JSON.stringify(messages)}
                  className={activeTab === TAB.CODE ? "" : "hidden"}
                  workspaceInfo={workspaceInfo}
                  activeFile={activeFileCodeEditor}
                  setActiveFile={setActiveFileCodeEditor}
                />
                <Terminal
                  ref={xtermRef}
                  className={activeTab === TAB.TERMINAL ? "" : "hidden"}
                />
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </LayoutGroup>
    </div>
  );
}
