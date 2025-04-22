"use client";

import { Terminal as XTerm } from "@xterm/xterm";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { Check, Code, Globe, Terminal as TerminalIcon, X } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { cloneDeep } from "lodash";

import Browser from "@/components/browser";
import CodeEditor, { ROOT_PATH } from "@/components/code-editor";
import QuestionInput from "@/components/question-input";
import SearchBrowser from "@/components/search-browser";
import Terminal from "@/components/terminal";
import { Button } from "@/components/ui/button";
import { ActionStep, AgentEvent, TOOL } from "@/typings/agent";
import Action from "@/components/action";
import Markdown from "@/components/markdown";

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
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isInChatView, setIsInChatView] = useState(false);
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [activeTab, setActiveTab] = useState(TAB.BROWSER);
  const [currentActionData, setCurrentActionData] = useState<ActionStep>();
  const [activeFileCodeEditor, setActiveFileCodeEditor] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const xtermRef = useRef<XTerm | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [isCompleted, setIsCompleted] = useState(false);

  const handleClickAction = (
    data: ActionStep | undefined,
    showTabOnly = false
  ) => {
    if (!data) return;

    setActiveFileCodeEditor("");

    switch (data.type) {
      case TOOL.TAVILY_SEARCH:
        setActiveTab(TAB.BROWSER);
        setCurrentActionData(data);
        break;

      case TOOL.TAVILY_VISIT:
      case TOOL.BROWSER_USE:
        setActiveTab(TAB.BROWSER);
        setCurrentActionData(data);
        break;

      case TOOL.BASH:
        setActiveTab(TAB.TERMINAL);
        if (!showTabOnly) {
          setTimeout(() => {
            // query
            xtermRef.current?.write(data.data.tool_input?.command + "");
            // result
            if (data.data.result) {
              xtermRef.current?.write("\r\n");
              xtermRef.current?.write(`${data.data.result}`);
              xtermRef.current?.write("\r\n$ ");
            } else {
              xtermRef.current?.write("\r\n$ ");
            }
          }, 500);
        }
        break;

      case TOOL.FILE_WRITE:
      case TOOL.STR_REPLACE_EDITOR:
        setActiveTab(TAB.CODE);
        setCurrentActionData(data);
        if (data.data.tool_input?.path) {
          setActiveFileCodeEditor(`${data.data.tool_input.path}`);
        }
        break;

      default:
        break;
    }
  };

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
    let ws = socket;

    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Create WebSocket connection if it doesn't exist or is not open
      ws = new WebSocket(`${process.env.NEXT_PUBLIC_API_URL}/ws`);
      setSocket(ws);

      ws.onopen = () => {
        ws?.send(
          JSON.stringify({
            type: "query",
            content: {
              text: newQuestion,
              resume: messages.length > 0,
            },
          })
        );
      };
    } else {
      // WebSocket is already open, send message directly
      ws.send(
        JSON.stringify({
          type: "query",
          content: {
            text: newQuestion,
          },
        })
      );
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case AgentEvent.PROCESSING:
            setIsLoading(true);
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

          case TOOL.BROWSER_USE:
            setMessages((prev) => {
              const lastMessage = cloneDeep(prev[prev.length - 1]);
              if (!data.content.screenshot) {
                return prev;
              }
              if (
                lastMessage.action &&
                lastMessage.action?.type === data.type
              ) {
                lastMessage.action.data.result = data.content.screenshot;
                setTimeout(() => {
                  handleClickAction(lastMessage.action);
                }, 500);
                return [...prev];
              } else {
                return [...prev, { ...lastMessage, action: data.content }];
              }
            });
            break;

          case AgentEvent.TOOL_RESULT:
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
                    lastMessage.action.data.result = data.content.result;
                    setTimeout(() => {
                      handleClickAction(lastMessage.action);
                    }, 500);
                    return [...prev];
                  } else {
                    return [...prev, { ...lastMessage, action: data.content }];
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

          default:
            break;
        }
      } catch (error) {
        console.error("Error parsing WebSocket data:", error);
        setIsLoading(false);
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      toast.error("An error occurred");
      ws.close();
      setIsLoading(false);
    };

    ws.onclose = () => {
      setSocket(null);
    };
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
    url += `/?folder=${ROOT_PATH}`;
    window.open(url, "_blank");
  };

  const parseJson = (jsonString: string) => {
    try {
      return JSON.parse(jsonString);
    } catch {
      return null;
    }
  };

  useEffect(() => {
    return () => {
      if (socket) {
        socket.close();
      }
    };
  }, [socket]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages?.length]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen dark:bg-slate-850">
      <div className={`flex justify-between w-full p-4`}>
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
              src="/logo.png"
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
              <motion.div
                className="p-4 pt-0 col-span-4 w-full max-h-[calc(100vh-78px)] pb-[160px] overflow-y-auto relative"
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
                    {message.content && (
                      <motion.div
                        className={`inline-block text-left rounded-lg ${
                          message.role === "user"
                            ? "bg-neutral-800 p-3 text-white max-w-[80%] border border-[#ffffff0f] shadow-[0px_0px_8px_0px_rgba(0,0,0,0.02)]"
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
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
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

                <motion.div
                  className="fixed bottom-0 left-0 w-[40%]"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2, duration: 0.3 }}
                >
                  <QuestionInput
                    className="px-6 py-4"
                    textareaClassName="h-30"
                    placeholder="Ask me anything..."
                    value={currentQuestion}
                    setValue={setCurrentQuestion}
                    handleKeyDown={handleKeyDown}
                    handleSubmit={handleQuestionSubmit}
                  />
                </motion.div>
              </motion.div>

              <motion.div className="col-span-6 bg-neutral-800 p-4 rounded-2xl border border-[#ffffff0f] shadow-[0px_0px_8px_0px_rgba(0,0,0,0.02)]">
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
                  screenshot={currentActionData?.data.result as string}
                  rawData={
                    currentActionData?.type === TOOL.TAVILY_VISIT &&
                    parseJson(currentActionData?.data?.result as string)
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
