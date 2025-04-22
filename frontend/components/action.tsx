"use client";

import { ActionStep, TOOL } from "@/typings/agent";
import { Code, Globe, Lightbulb, Search, Terminal } from "lucide-react";
import { useMemo } from "react";

interface ActionProps {
  type: TOOL;
  value: ActionStep["data"];
  onClick: () => void;
}

const Action = ({ type, value, onClick }: ActionProps) => {
  const step_icon = useMemo(() => {
    const className =
      "h-4 w-4 text-neutral-500 dark:text-neutral-100 flex-shrink-0 mt-[2px]";
    switch (type) {
      case TOOL.SEQUENTIAL_THINKING:
        return <Lightbulb className={className} />;
      case TOOL.TAVILY_SEARCH:
        return <Search className={className} />;
      case TOOL.TAVILY_VISIT:
      case TOOL.BROWSER_USE:
        return <Globe className={className} />;
      case TOOL.BASH:
        return <Terminal className={className} />;
      case TOOL.FILE_WRITE:
        return <Code className={className} />;
      case TOOL.STR_REPLACE_EDITOR:
        return <Code className={className} />;

      default:
        return <></>;
    }
  }, [type]);

  const step_title = useMemo(() => {
    switch (type) {
      case TOOL.SEQUENTIAL_THINKING:
        return "Thinking";
      case TOOL.TAVILY_SEARCH:
        return "Searching";
      case TOOL.TAVILY_VISIT:
      case TOOL.BROWSER_USE:
        return "Browsing";
      case TOOL.BASH:
        return "Executing Command";
      case TOOL.FILE_WRITE:
        return "Creating File";
      case TOOL.STR_REPLACE_EDITOR:
        return value?.tool_input?.command === "create"
          ? "Creating File"
          : "Editing File";

      default:
        break;
    }
  }, [type, value?.tool_input?.command]);

  const step_value = useMemo(() => {
    switch (type) {
      case TOOL.SEQUENTIAL_THINKING:
        return value.tool_input?.thought;
      case TOOL.TAVILY_SEARCH:
        return value.tool_input?.query;
      case TOOL.TAVILY_VISIT:
        return value.tool_input?.url;
      case TOOL.BROWSER_USE:
        return value.tool_input?.url;
      case TOOL.BASH:
        return value.tool_input?.command;
      case TOOL.FILE_WRITE:
        return value.tool_input?.file;
      case TOOL.STR_REPLACE_EDITOR:
        return value.tool_input?.path;

      default:
        break;
    }
  }, [type, value]);

  if (type === TOOL.COMPLETE) return null;

  return (
    <div
      onClick={onClick}
      className="group cursor-pointer flex items-start gap-2 px-3 py-2 bg-neutral-50 dark:bg-neutral-800 rounded-xl backdrop-blur-sm 
      border border-[#ffffff0f] shadow-[0px_0px_8px_0px_rgba(0,0,0,0.02)]
      transition-all duration-200 ease-out
      hover:bg-neutral-100 dark:hover:bg-neutral-800
      hover:border-neutral-300 dark:hover:border-neutral-700
      hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:hover:shadow-[0_2px_8px_rgba(0,0,0,0.24)]
      active:scale-[0.98] overflow-hidden"
    >
      {step_icon}
      <div className="flex flex-col gap-1.5 text-sm">
        <span className="text-neutral-900 dark:text-neutral-100 font-medium group-hover:text-neutral-800 dark:group-hover:text-white">
          {step_title}
        </span>
        <span className="text-neutral-500 dark:text-neutral-400 font-medium truncate group-hover:text-neutral-600 dark:group-hover:text-neutral-300">
          {step_value}
        </span>
      </div>
    </div>
  );
};

export default Action;
