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
import { ActionStep, ThoughtType } from "@/typings/agent";
import Action from "@/components/action";

enum TAB {
  BROWSER = "browser",
  CODE = "code",
  TERMINAL = "terminal",
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content?: string;
  action?: ActionStep;
  timestamp: number;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isInChatView, setIsInChatView] = useState(false);
  const [streamedResponse, setStreamedResponse] = useState("");
  const [eventSourceInstance, setEventSourceInstance] =
    useState<EventSource | null>(null);
  const [reasoningData, setReasoningData] = useState([""]);
  const [activeTab, setActiveTab] = useState(TAB.BROWSER);
  const [currentActionData, setCurrentActionData] = useState<ActionStep>();
  const [activeFileCodeEditor, setActiveFileCodeEditor] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const xtermRef = useRef<XTerm | null>(null);

  const handleClickAction = (
    data: ActionStep | undefined,
    showTabOnly = false
  ) => {
    if (!data) return;

    switch (data.type) {
      case ThoughtType.SEARCH:
        setActiveTab(TAB.BROWSER);
        setCurrentActionData(data);
        break;

      case ThoughtType.VISIT:
        setActiveTab(TAB.BROWSER);
        setCurrentActionData(data);
        break;

      case ThoughtType.EXECUTE_COMMAND:
        setActiveTab(TAB.TERMINAL);
        if (!showTabOnly) {
          setTimeout(() => {
            xtermRef.current?.write(data.data.query + "");
            xtermRef.current?.write("\r\n$ ");
          }, 500);
        }
        break;

      case ThoughtType.CREATE_FILE:
      case ThoughtType.EDIT_FILE:
        setActiveTab(TAB.CODE);
        setCurrentActionData(data);
        if (data.data.query) {
          setActiveFileCodeEditor(`${ROOT_PATH}/${data.data.query}`);
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

    const encodedQuestion = encodeURIComponent(newQuestion);
    const eventSource = new EventSource(
      `${process.env.NEXT_PUBLIC_API_URL}/search?question=${encodedQuestion}`
    );
    setEventSourceInstance(eventSource);

    if (eventSource) {
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          switch (data.type) {
            case ThoughtType.START:
              setStreamedResponse("");
              break;

            case ThoughtType.WRITING_REPORT:
              setStreamedResponse(data.data.final_report);
              break;

            case "complete":
              // Add assistant message when complete
              const newAssistantMessage: Message = {
                id: Date.now().toString(),
                role: "assistant",
                content: data.data.final_report,
                timestamp: Date.now(),
              };
              setMessages((prev) => [...prev, newAssistantMessage]);
              setStreamedResponse(data.data.final_report);
              eventSource.close();
              setIsLoading(false);
              break;

            case ThoughtType.TOOL:
              setReasoningData((prev) => [...prev, ""]);
              break;

            case ThoughtType.REASONING:
              setReasoningData((prev) => {
                const lastItem = prev[prev.length - 1];
                return [...prev.slice(0, -1), lastItem + data.data.reasoning];
              });
              break;

            default:
              break;
          }
        } catch (error) {
          console.error("Error parsing SSE data:", error);
          setIsLoading(false);
        }
      };

      eventSource.onerror = () => {
        toast.error("An error occurred");
        eventSource.close();
        setIsLoading(false);
      };
    }

    handleMockData();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleQuestionSubmit((e.target as HTMLTextAreaElement).value);
    }
  };

  const resetChat = () => {
    eventSourceInstance?.close();
    setIsInChatView(false);
    setStreamedResponse("");
    setReasoningData([""]);
    setMessages([]);
    setIsLoading(false);
  };

  const handleOpenVSCode = () => {
    const url = process.env.NEXT_PUBLIC_ROOT_PATH || "http://localhost:8080";
    window.open(url, "_blank");
  };

  const handleMockData = () => {
    const actions = [
      {
        type: ThoughtType.SEARCH,
        data: {
          query: "Group Relative Policy Optimization reinforcement learning",
        },
      },
      {
        type: ThoughtType.VISIT,
        data: {
          url: "https://arxiv.org/pdf/2402.03300",
          screenshot: "/arxiv.webp",
        },
      },
      {
        type: ThoughtType.EXECUTE_COMMAND,
        data: {
          query: "mkdir -p research && cd research && touch todo.md",
        },
      },
      {
        type: ThoughtType.CREATE_FILE,
        data: {
          query: "todo.md",
        },
      },
      {
        type: ThoughtType.EDIT_FILE,
        data: {
          query: "todo.md",
        },
      },
      {
        type: ThoughtType.EXECUTE_COMMAND,
        data: {
          query: "vim todo.md",
        },
      },
    ];

    let currentIndex = 0;
    const interval = setInterval(() => {
      if (currentIndex >= actions.length) {
        clearInterval(interval);
        return;
      }

      const nextAction = actions[currentIndex];
      setMessages((prevMessages) => [
        ...prevMessages,
        {
          id: Date.now().toString(),
          role: "assistant",
          action: nextAction,
          timestamp: Date.now(),
        },
      ]);

      setTimeout(() => {
        handleClickAction(nextAction);
      }, 500);

      currentIndex++;
    }, 2000);
  };

  useEffect(() => {
    return () => {
      if (eventSourceInstance) {
        eventSourceInstance.close();
      }
    };
  }, [eventSourceInstance]);

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
                        className={`inline-block p-3 max-w-[80%] text-left rounded-lg ${
                          message.role === "user"
                            ? "bg-white text-black"
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
                        {message.content}
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
                          value={message.action.data.query || ""}
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
                      currentActionData?.type === ThoughtType.VISIT
                        ? ""
                        : "hidden"
                    }
                    url={currentActionData?.data.url}
                    screenshot={currentActionData?.data.screenshot}
                  />
                  <SearchBrowser
                    className={
                      activeTab === TAB.BROWSER &&
                      currentActionData?.type === ThoughtType.SEARCH
                        ? ""
                        : "hidden"
                    }
                    keyword={currentActionData?.data.query}
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
