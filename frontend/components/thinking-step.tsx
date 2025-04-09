"use client";

import { useMemo } from "react";
import {
  BookOpen,
  Check,
  Globe,
  Lightbulb,
  List,
  NotebookPen,
  Pencil,
  Search,
} from "lucide-react";

import { ThoughtStep, ThoughtType } from "@/typings/agent";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

interface IThinkingStepProps {
  value: ThoughtStep;
  sources: {
    [key: string]: {
      url: string;
      result: {
        content: string;
      };
    };
  };
  hideTitle?: boolean;
}

const ThinkingStep = ({ value, sources, hideTitle }: IThinkingStepProps) => {
  const step_icon = useMemo(() => {
    const className = "size-3 mt-1";
    switch (value?.type) {
      case ThoughtType.THINKING:
        return <Lightbulb className={className} />;
      case ThoughtType.SEARCH:
        return <Search className={className} />;
      case ThoughtType.SEARCH_RESULTS:
        return <List className={className} />;
      case ThoughtType.VISIT:
        return <Globe className={className} />;
      case ThoughtType.DRAFT_ANSWER:
        return <Pencil className={className} />;
      case ThoughtType.EVAL_ANSWER:
        return <Check className={className} />;
      case ThoughtType.GENERATING_REPORT:
        return <NotebookPen className={className} />;

      default:
        return <></>;
    }
  }, [value?.type]);

  const step_title = useMemo(() => {
    switch (value?.type) {
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

      default:
        break;
    }
  }, [value?.type]);

  if (!value) return null;

  return (
    <ul className={`${hideTitle ? "mb-4" : "pl-2"} space-y-2 animate-fade-in`}>
      <li>
        {!hideTitle && (
          <div className="flex items-start gap-x-2">
            {step_icon}
            <span className="flex-1 space-x-1">
              <b className="text-md">{step_title}:</b>
              <span>
                {value.data?.thinking?.replace(
                  /<url-(\d+)>/g,
                  (_, num) => sources[`<url-${num}>`]?.url || ""
                )}
              </span>
            </span>
          </div>
        )}
        {value.data.answer && value?.type === ThoughtType.DRAFT_ANSWER && (
          <div className="pl-4 mt-2">
            <Tooltip>
              <TooltipTrigger>
                <p
                  className="flex items-center gap-x-2 text-xs bg-neutral-950 rounded-full px-2 py-1 animate-fade-in max-w-[300px]"
                  style={{ animationDelay: `${100}ms` }}
                >
                  <BookOpen className="size-3 text-white" />{" "}
                  <span className="truncate flex-1">{value.data.answer}</span>
                </p>
              </TooltipTrigger>
              <TooltipContent>
                <p>{value.data.answer}</p>
              </TooltipContent>
            </Tooltip>
          </div>
        )}
        {value.data?.queries && (
          <div
            className={`flex gap-2 flex-wrap items-start mt-2 animate-fade-in ${
              hideTitle ? "" : "pl-4"
            }`}
          >
            {value.data?.queries?.map((query, index) => (
              <p
                key={index}
                className={`flex items-center gap-x-2 text-xs ${
                  hideTitle ? "bg-neutral-800" : "bg-neutral-950"
                } rounded-full px-2 py-1 animate-fade-in`}
                style={{ animationDelay: `${index * 100}ms` }}
              >
                <Search className="size-3" />{" "}
                <span className="flex-1">{query}</span>
              </p>
            ))}
          </div>
        )}
        {value.data?.urls && (
          <div
            className={`flex gap-2 flex-col items-start mt-2 animate-fade-in ${
              hideTitle ? "" : "pl-4"
            }`}
          >
            {value.data.urls?.map((source, index) => (
              <a
                key={index}
                href={source}
                target="_blank"
                rel="noreferrer"
                className={`flex items-center gap-x-2 text-xs ${
                  hideTitle ? "bg-neutral-800" : "bg-neutral-950"
                } rounded-full px-2 py-1 animate-fade-in`}
                style={{ animationDelay: `${index * 100}ms` }}
              >
                <Globe className="size-3" />{" "}
                <span className="flex-1">{source}</span>
              </a>
            ))}
          </div>
        )}
        {value.data?.results && (
          <div className="flex gap-2 flex-col items-start mt-2 animate-fade-in pl-4">
            {value.data.results?.map((source, index) => (
              <Tooltip key={index}>
                <TooltipTrigger>
                  <a
                    key={index}
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-x-2 text-xs bg-neutral-950 rounded-full px-2 py-1 animate-fade-in"
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <Globe className="size-3" />{" "}
                    <span className="flex-1">{source.title}</span>
                  </a>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{source.description}</p>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        )}
      </li>
    </ul>
  );
};

export default ThinkingStep;
