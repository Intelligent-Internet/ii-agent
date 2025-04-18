"use client";

import { Terminal as XTerm } from "@xterm/xterm";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { Code, Globe, Terminal as TerminalIcon, X } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import Browser from "@/components/browser";
import CodeEditor, { ROOT_PATH } from "@/components/code-editor";
import QuestionInput from "@/components/question-input";
import SearchBrowser from "@/components/search-browser";
import Terminal from "@/components/terminal";
import { Button } from "@/components/ui/button";
import { ActionStep, AgentEvent, TOOL } from "@/typings/agent";
import Action from "@/components/action";
import Markdown from "@/components/markdown";
import { cloneDeep } from "lodash";

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
  const [streamedResponse, setStreamedResponse] = useState("");
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [reasoningData, setReasoningData] = useState([""]);
  const [activeTab, setActiveTab] = useState(TAB.BROWSER);
  const [currentActionData, setCurrentActionData] = useState<ActionStep>();
  const [activeFileCodeEditor, setActiveFileCodeEditor] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const xtermRef = useRef<XTerm | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

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
        setActiveTab(TAB.BROWSER);
        setCurrentActionData(data);
        break;

      case TOOL.BASH:
        setActiveTab(TAB.TERMINAL);
        if (!showTabOnly) {
          setTimeout(() => {
            xtermRef.current?.write(data.data.tool_input?.command + "");
            xtermRef.current?.write("\r\n$ ");
          }, 500);
        }
        break;

      case TOOL.FILE_WRITE:
      case TOOL.STR_REPLACE_EDITOR:
        setActiveTab(TAB.CODE);
        setCurrentActionData(data);
        if (data.data.tool_input?.path) {
          setActiveFileCodeEditor(`${ROOT_PATH}/${data.data.tool_input.path}`);
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

    const newUserMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: newQuestion,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, newUserMessage]);

    // Create WebSocket connection
    const ws = new WebSocket(`${process.env.NEXT_PUBLIC_API_URL}/ws`);
    setSocket(ws);

    ws.onopen = () => {
      // Send the question when connection is established
      ws.send(
        JSON.stringify({
          type: "query",
          content: {
            text: newQuestion,
            resume: false,
          },
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

          case AgentEvent.TOOL_RESULT:
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
    setStreamedResponse("");
    setReasoningData([""]);
    setMessages([]);
    setIsLoading(false);
  };

  const handleOpenVSCode = () => {
    let url = process.env.NEXT_PUBLIC_ROOT_PATH || "http://localhost:8080";
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
      <div
        className={`flex justify-between w-full px-6 py-4 ${
          isInChatView && "border-b border-neutral-500"
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
              src="/logo.png"
              alt="II-Agent Logo"
              width={40}
              height={40}
              className="rounded-sm"
            />
          )}
          II-Agent
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
              className="w-full grid grid-cols-10 write-report shadow-lg overflow-hidden flex-1"
            >
              <motion.div
                className="p-4 col-span-4 w-full max-h-[calc(100vh-78px)] pb-[160px] overflow-y-auto relative"
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
                        className={`inline-block p-3 text-left rounded-lg ${
                          message.role === "user"
                            ? "bg-white text-black max-w-[80%]"
                            : "bg-neutral-800 text-white"
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

                {isLoading && streamedResponse && (
                  <motion.div
                    className="mb-4 text-left"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <motion.div className="inline-block p-3 max-w-[80%] text-left rounded-lg bg-neutral-800 text-white">
                      {streamedResponse}
                    </motion.div>
                  </motion.div>
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

              {reasoningData && (
                <motion.div className="col-span-6 border-l border-neutral-500">
                  <div className="p-4 bg-neutral-850 flex items-center justify-between">
                    <div className="flex gap-x-4">
                      <Button
                        className={`cursor-pointer ${
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
                        className={`cursor-pointer ${
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
                        className={`cursor-pointer ${
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
                      currentActionData?.type === TOOL.TAVILY_VISIT
                        ? ""
                        : "hidden"
                    }
                    url={currentActionData?.data?.tool_input?.url}
                    // screenshot={currentActionData?.data.result as string}
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
                    className={activeTab === TAB.CODE ? "" : "hidden"}
                    activeFile={activeFileCodeEditor}
                    setActiveFile={setActiveFileCodeEditor}
                  />
                  <Terminal
                    ref={xtermRef}
                    className={activeTab === TAB.TERMINAL ? "" : "hidden"}
                  />
                </motion.div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </LayoutGroup>
    </div>
  );
}
