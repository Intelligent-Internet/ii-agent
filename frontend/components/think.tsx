import { ThoughtStep } from "@/typings/agent";
import ThinkingStep from "./thinking-step";
import React from "react";
import { Loader2 } from "lucide-react";
import { Lightbulb } from "lucide-react";

interface ThinkProps {
  data: string[];
  thoughtData: ThoughtStep[];
  sources: {
    [key: string]: {
      url: string;
      result: { content: string };
    };
  };
  isStreamingThought: boolean;
}

const Think = ({
  data,
  thoughtData,
  sources,
  isStreamingThought,
}: ThinkProps) => {
  return (
    <div className="h-full px-4 w-[400px] border-l border-neutral-500 max-h-[calc(100vh-128px)] overflow-y-auto">
      <div className="text-white whitespace-pre-wrap">
        <span className="flex items-center gap-x-2">
          {isStreamingThought ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Lightbulb />
          )}{" "}
          Thoughts
        </span>
        {data.map((item, index) => (
          <div key={index}>
            <p>{item.replaceAll(/```(?:py|python)?\s*(.*?)\s*```/g, "")}</p>
            {thoughtData?.[index] && (
              <ThinkingStep
                hideTitle
                value={thoughtData[index]}
                sources={sources}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default Think;
