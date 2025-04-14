"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { Code, Copy, Globe, Terminal as TerminalIcon, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import Image from "next/image";
import { Terminal as XTerm } from "@xterm/xterm";

import CodeEditor from "@/components/code-editor";
import Markdown from "@/components/markdown";
import QuestionInput from "@/components/question-input";
import { Button } from "@/components/ui/button";
import { ActionStep, ThoughtStep, ThoughtType } from "@/typings/agent";
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
  const [thoughtData, setThoughtData] = useState<ThoughtStep[]>([]);
  const [isStreamingThought, setIsStreamingThought] = useState(false);
  const [streamedResponse, setStreamedResponse] = useState("");
  const [eventSourceInstance, setEventSourceInstance] =
    useState<EventSource | null>(null);
  const [reasoningData, setReasoningData] = useState([""]);
  const [activeTab, setActiveTab] = useState(TAB.BROWSER);
  const [currentActionData, setCurrentActionData] = useState<ActionStep>();
  const xtermRef = useRef<XTerm | null>(null);

  const [sources, setSources] = useState<{
    [key: string]: {
      url: string;
      result: {
        content: string;
      };
    };
  }>({});
  const [modelType, setModelType] = useState("reasoning");

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
        break;

      default:
        break;
    }
  };

  const handleSubmit = () => {
    if (!question.trim()) return;

    setIsInChatView(true);
    setIsStreamingThought(true);

    const encodedQuestion = encodeURIComponent(question);
    const eventSource = new EventSource(
      `${
        process.env.NEXT_PUBLIC_API_URL
      }/search?question=${encodedQuestion}&is_reasoning=${
        modelType == "reasoning"
      }`
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
              if (data.data.name == "web_search") {
                setThoughtData((prev) => [
                  ...prev,
                  {
                    type: ThoughtType.SEARCH,
                    data: {
                      queries: data.data.arguments.queries,
                    },
                    timestamp: data.data.timestamp,
                  },
                ]);
              }
              if (data.data.name == "page_visit") {
                setThoughtData((prev) => [
                  ...prev,
                  {
                    type: ThoughtType.VISIT,
                    data: {
                      urls: data.data.arguments.urls,
                    },
                    timestamp: data.data.timestamp,
                  },
                ]);
              }
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
                setThoughtData((prev) => [
                  ...prev,
                  {
                    type: ThoughtType.VISIT,
                    data: {
                      results: data.data.results.map(
                        (item: {
                          url: string;
                          result: { content: string };
                        }) => ({
                          url: item.url,
                          title: item.url,
                          description: item.result.content,
                        })
                      ),
                    },
                    timestamp: data.timestamp,
                  },
                ]);
              }
              break;

            case ThoughtType.WRITING_REPORT:
              setIsStreamingThought(false);
              setStreamedResponse(data.data.final_report);
              break;

            case "complete":
              setStreamedResponse(data.data.final_report);
              eventSource.close();
              break;
            default:
              setThoughtData((prev) => [...prev, data]);
              break;
          }
        } catch (error) {
          console.error("Error parsing SSE data:", error);
        }
      };

      eventSource.onerror = () => {
        toast.error("An error occurred");
        setIsStreamingThought(false);
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
    setThoughtData([]);
    setIsStreamingThought(false);
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
              modelType={modelType}
              setModelType={setModelType}
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
                {/* <Thoughts
                  isStreamingThought={isStreamingThought}
                  thoughtData={thoughtData}
                  sources={sources}
                /> */}
                <div className="flex flex-col items-start gap-y-4">
                  {`I'll help you explore how to incorporate expert demonstrations
                  into Group Relative Policy Optimization (Group RPO) to enhance
                  sample efficiency. I'll research this topic thoroughly and
                  provide you with a comprehensive analysis. Let me get started
                  right away.`}
                  <Action
                    type={ThoughtType.SEARCH}
                    value="Group Relative Policy Optimization reinforcement learning"
                    onClick={() =>
                      handleClickAction({
                        type: ThoughtType.SEARCH,
                        data: {
                          query:
                            "Group Relative Policy Optimization reinforcement learning",
                        },
                      })
                    }
                  />
                  <Action
                    type={ThoughtType.VISIT}
                    value="https://arxiv.org/pdf/2402.03300"
                    onClick={() =>
                      handleClickAction({
                        type: ThoughtType.VISIT,
                        data: {
                          url: "https://arxiv.org/pdf/2402.03300",
                          screenshot: "/arxiv.webp",
                        },
                      })
                    }
                  />
                  <Action
                    type={ThoughtType.EXECUTE_COMMAND}
                    value="mkdir -p research && cd research && touch todo.md"
                    onClick={() =>
                      handleClickAction({
                        type: ThoughtType.EXECUTE_COMMAND,
                        data: {
                          query:
                            "mkdir -p research && cd research && touch todo.md",
                        },
                      })
                    }
                  />
                  <Action
                    type={ThoughtType.CREATE_FILE}
                    value="todo.md"
                    onClick={() =>
                      handleClickAction({
                        type: ThoughtType.CREATE_FILE,
                        data: {
                          query: "todo.md",
                        },
                      })
                    }
                  />
                  <Action
                    type={ThoughtType.EDIT_FILE}
                    value="todo.md"
                    onClick={() =>
                      handleClickAction({
                        type: ThoughtType.EDIT_FILE,
                        data: {
                          query: "todo.md",
                        },
                      })
                    }
                  />
                </div>

                {streamedResponse ? (
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
                ) : (
                  thoughtData.length > 0 &&
                  !isStreamingThought && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex items-center space-x-2 p-3 bg-neutral-800 rounded-lg w-fit"
                    >
                      <span className="text-sm text-gray-300">
                        Writing report
                      </span>
                      <span className="flex space-x-1">
                        {[0, 1, 2].map((i) => (
                          <motion.span
                            key={i}
                            className="w-1.5 h-1.5 bg-gray-300 rounded-full"
                            initial={{ opacity: 0.3 }}
                            animate={{ opacity: 1 }}
                            transition={{
                              repeat: Infinity,
                              repeatType: "reverse",
                              duration: 0.4,
                              delay: i * 0.15,
                            }}
                          />
                        ))}
                      </span>
                    </motion.div>
                  )
                )}
              </motion.div>

              {modelType == "reasoning" && reasoningData && (
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
