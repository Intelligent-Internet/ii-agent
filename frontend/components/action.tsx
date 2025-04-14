"use client";

import { ThoughtType } from "@/typings/agent";
import {
  Check,
  Code,
  Globe,
  Lightbulb,
  NotebookPen,
  Pencil,
  Search,
  Terminal,
} from "lucide-react";
import { useMemo } from "react";

interface ActionProps {
  type: ThoughtType;
  value: string;
  onClick: () => void;
}

const Action = ({ type, value, onClick }: ActionProps) => {
  const step_icon = useMemo(() => {
    const className =
      "h-4 w-4 text-neutral-500 dark:text-neutral-100 flex-shrink-0";
    switch (type) {
      case ThoughtType.THINKING:
        return <Lightbulb className={className} />;
      case ThoughtType.SEARCH:
        return <Search className={className} />;
      case ThoughtType.SEARCH_RESULTS:
        return <Search className={className} />;
      case ThoughtType.VISIT:
        return <Globe className={className} />;
      case ThoughtType.DRAFT_ANSWER:
        return <Pencil className={className} />;
      case ThoughtType.EVAL_ANSWER:
        return <Check className={className} />;
      case ThoughtType.GENERATING_REPORT:
        return <NotebookPen className={className} />;
      case ThoughtType.EXECUTE_COMMAND:
        return <Terminal className={className} />;
      case ThoughtType.CREATE_FILE:
        return <Code className={className} />;
      case ThoughtType.EDIT_FILE:
        return <Code className={className} />;

      default:
        return <></>;
    }
  }, [type]);

  const step_title = useMemo(() => {
    switch (type) {
      case ThoughtType.THINKING:
        return "Thinking";
      case ThoughtType.SEARCH:
        return "Searching";
      case ThoughtType.SEARCH_RESULTS:
        return "Search Results";
      case ThoughtType.VISIT:
        return "Browsing";
      case ThoughtType.DRAFT_ANSWER:
        return "Drafting Answer";
      case ThoughtType.EVAL_ANSWER:
        return "Evaluating Answer";
      case ThoughtType.GENERATING_REPORT:
        return "Writing Report";
      case ThoughtType.EXECUTE_COMMAND:
        return "Executing Command";
      case ThoughtType.CREATE_FILE:
        return "Creating File";
      case ThoughtType.EDIT_FILE:
        return "Editing File";

      default:
        break;
    }
  }, [type]);

  return (
    <div
      onClick={onClick}
      className="group cursor-pointer flex items-center gap-2 px-3 py-2 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-xl backdrop-blur-sm 
      transition-all duration-200 ease-out
      hover:bg-neutral-100 dark:hover:bg-neutral-800
      hover:border-neutral-300 dark:hover:border-neutral-700
      hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:hover:shadow-[0_2px_8px_rgba(0,0,0,0.24)]
      active:scale-[0.98]"
    >
      {step_icon}
      <div className="flex gap-1.5 text-sm">
        <span className="text-neutral-900 dark:text-neutral-100 font-medium group-hover:text-neutral-800 dark:group-hover:text-white">
          {step_title}
        </span>
        <span className="text-neutral-500 dark:text-neutral-400 font-medium truncate pl-1 group-hover:text-neutral-600 dark:group-hover:text-neutral-300">
          {value}
        </span>
      </div>
    </div>
  );
};

export default Action;
