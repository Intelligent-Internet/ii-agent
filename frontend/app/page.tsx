"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { Code, Copy, Globe, Terminal as TerminalIcon, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import Image from "next/image";
import { Terminal as XTerm } from "@xterm/xterm";

import CodeEditor, { ROOT_PATH } from "@/components/code-editor";
import Markdown from "@/components/markdown";
import QuestionInput from "@/components/question-input";
import { Button } from "@/components/ui/button";
import { ActionStep, ThoughtType } from "@/typings/agent";
import Terminal from "@/components/terminal";
import Browser from "@/components/browser";
import SearchBrowser from "@/components/search-browser";
import Action from "@/components/action";

enum TAB {
  BROWSER = "browser",
  CODE = "code",
  TERMINAL = "terminal",
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [isInChatView, setIsInChatView] = useState(false);
  const [streamedResponse, setStreamedResponse] = useState("");
  const [eventSourceInstance, setEventSourceInstance] =
    useState<EventSource | null>(null);
  const [reasoningData, setReasoningData] = useState([""]);
  const [activeTab, setActiveTab] = useState(TAB.BROWSER);
  const [currentActionData, setCurrentActionData] = useState<ActionStep>();
  const [actions, setActions] = useState<ActionStep[]>([]);
  const [activeFileCodeEditor, setActiveFileCodeEditor] = useState("");
  const xtermRef = useRef<XTerm | null>(null);

  const [sources, setSources] = useState<{
    [key: string]: {
      url: string;
      result: {
        content: string;
      };
    };
  }>({});

  const handleClickAction = (data: ActionStep) => {
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
        setTimeout(() => {
          xtermRef.current?.write(data.data.query + "");
          xtermRef.current?.write("\r\n$ ");
        }, 500);
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

  const handleSubmit = () => {
    if (!question.trim()) return;

    setIsInChatView(true);

    const encodedQuestion = encodeURIComponent(question);
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
            case ThoughtType.STEP:
            case ThoughtType.STEP_COMPLETED:
            case ThoughtType.KNOWLEDGE:
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

            case ThoughtType.VISIT:
              if (data.data.results) {
                const urlResultMap = data.data.results.reduce(
                  (
                    acc: Record<
                      string,
                      {
                        url: string;
                        result: {
                          content: string;
                        };
                      }
                    >,
                    item: {
                      url: string;
                      result: {
                        content: string;
                      };
                    },
                    index: number
                  ) => ({
                    ...acc,
                    [data.data.urls[index]]: item.result,
                  }),
                  {}
                );
                setSources((prev) => ({
                  ...prev,
                  ...urlResultMap,
                }));
              }
              break;

            case ThoughtType.WRITING_REPORT:
              setStreamedResponse(data.data.final_report);
              break;

            case "complete":
              setStreamedResponse(data.data.final_report);
              eventSource.close();
              break;
            default:
              break;
          }
        } catch (error) {
          console.error("Error parsing SSE data:", error);
        }
      };

      eventSource.onerror = () => {
        toast.error("An error occurred");
        eventSource.close();
      };
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const resetChat = () => {
    eventSourceInstance?.close();
    setIsInChatView(false);
    setQuestion("");
    setStreamedResponse("");
    setReasoningData([""]);
  };

  const handleOpenVSCode = () => {
    const url = process.env.NEXT_PUBLIC_ROOT_PATH || "http://localhost:8080";
    window.open(url, "_blank");
  };

  useEffect(() => {
    return () => {
      if (eventSourceInstance) {
        eventSourceInstance.close();
      }
    };
  }, [eventSourceInstance]);

  useEffect(() => {
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

    setActions([]);

    const interval = setInterval(() => {
      let nextAction: ActionStep | undefined = undefined;
      setActions((prevActions) => {
        if (prevActions.length < actions.length) {
          nextAction = actions[prevActions.length];
          return [...prevActions, actions[prevActions.length]];
        } else {
          clearInterval(interval);
          return prevActions;
        }
      });
      setTimeout(() => {
        if (nextAction) {
          handleClickAction(nextAction);
        }
      }, 500);
    }, 2000);

    return () => clearInterval(interval);
  }, []);

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
              question={question}
              setQuestion={setQuestion}
              handleKeyDown={handleKeyDown}
              handleSubmit={handleSubmit}
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
                className="p-4 col-span-4 w-full max-h-[calc(100vh-78px)] overflow-y-auto"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2, duration: 0.3 }}
              >
                {question && (
                  <motion.div
                    className="mb-4 text-right"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1, duration: 0.3 }}
                  >
                    <motion.div
                      className={`inline-block p-3 max-w-[80%] text-left rounded-lg bg-white text-black`}
                      initial={{ scale: 0.9 }}
                      animate={{ scale: 1 }}
                      transition={{
                        type: "spring",
                        stiffness: 500,
                        damping: 30,
                      }}
                    >
                      {question}
                    </motion.div>
                  </motion.div>
                )}
                <div className="flex flex-col items-start gap-y-4">
                  {`I'll help you explore how to incorporate expert demonstrations
                  into Group Relative Policy Optimization (Group RPO) to enhance
                  sample efficiency. I'll research this topic thoroughly and
                  provide you with a comprehensive analysis. Let me get started
                  right away.`}
                  {actions?.map((action, index) => (
                    <Action
                      key={`${action.type}_${index}`}
                      type={action.type}
                      value={action.data.query || action.data.url || ""}
                      onClick={() => handleClickAction(action)}
                    />
                  ))}
                </div>

                {streamedResponse && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{
                      type: "spring",
                      stiffness: 300,
                      damping: 30,
                    }}
                    className={`inline-block p-4 rounded-lg text-md w-full bg-neutral-800 space-y-2 text-left relative`}
                  >
                    <Button
                      className="absolute top-4 right-4 cursor-pointer"
                      onClick={() => {
                        navigator.clipboard.writeText(streamedResponse);
                        toast.success("Copied to clipboard");
                      }}
                    >
                      <Copy className="size-4" />
                    </Button>
                    <Markdown>
                      {streamedResponse.replace(
                        /<url-(\d+)>/g,
                        (_, num) => sources[`<url-${num}>`]?.url || ""
                      )}
                    </Markdown>
                  </motion.div>
                )}
                <motion.div>
                  <QuestionInput
                    question={question}
                    setQuestion={setQuestion}
                    handleKeyDown={handleKeyDown}
                    handleSubmit={handleSubmit}
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
