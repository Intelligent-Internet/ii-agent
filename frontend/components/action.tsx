"use client";

import { ActionStep, TOOL } from "@/typings/agent";
import {
  Code,
  FileText,
  Globe,
  Lightbulb,
  Rocket,
  Search,
  Terminal,
} from "lucide-react";
import { useMemo } from "react";

interface ActionProps {
  workspaceInfo: string;
  type: TOOL;
  value: ActionStep["data"];
  onClick: () => void;
}

const Action = ({ workspaceInfo, type, value, onClick }: ActionProps) => {
  const step_icon = useMemo(() => {
    const className = "h-4 w-4 text-neutral-100 flex-shrink-0 mt-[2px]";
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
      case TOOL.STATIC_DEPLOY:
        return <Rocket className={className} />;
      case TOOL.PDF_TEXT_EXTRACT:
        return <FileText className={className} />;

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
          : value?.tool_input?.command === "view"
          ? "Viewing File"
          : "Editing File";
      case TOOL.STATIC_DEPLOY:
        return "Deploying";
      case TOOL.PDF_TEXT_EXTRACT:
        return "Extracting Text";

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
        return value.tool_input?.file === workspaceInfo
          ? workspaceInfo
          : value.tool_input?.file?.replace(workspaceInfo, "");
      case TOOL.STR_REPLACE_EDITOR:
        return value.tool_input?.path === workspaceInfo
          ? workspaceInfo
          : value.tool_input?.path?.replace(workspaceInfo, "");
      case TOOL.STATIC_DEPLOY:
        return value.tool_input?.file_path === workspaceInfo
          ? workspaceInfo
          : value.tool_input?.file_path?.replace(workspaceInfo, "");
      case TOOL.PDF_TEXT_EXTRACT:
        return value.tool_input?.file_path === workspaceInfo
          ? workspaceInfo
          : value.tool_input?.file_path?.replace(workspaceInfo, "");

      default:
        break;
    }
  }, [type, value, workspaceInfo]);

  if (type === TOOL.COMPLETE) return null;

  return (
    <div
      onClick={onClick}
      className="group cursor-pointer flex items-start gap-2 px-3 py-2 bg-[#35363a] rounded-xl backdrop-blur-sm 
      shadow-sm
      transition-all duration-200 ease-out
      hover:bg-neutral-800
      hover:border-neutral-700
      hover:shadow-[0_2px_8px_rgba(0,0,0,0.24)]
      active:scale-[0.98] overflow-hidden"
    >
      {step_icon}
      <div className="flex flex-col gap-1.5 text-sm">
        <span className="text-neutral-100 font-medium group-hover:text-white">
          {step_title}
        </span>
        <span className="text-neutral-400 font-medium truncate group-hover:text-neutral-300">
          {step_value}
        </span>
      </div>
    </div>
  );
};

export default Action;
