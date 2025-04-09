export type Source = {
  title: string;
  url: string;
};

export enum ThoughtType {
  START = "start",
  STEP = "step",
  STEP_COMPLETED = "step_completed",
  REASONING = "reasoning",
  THINKING = "thinking",
  KNOWLEDGE = "knowledge",
  SEARCH = "search",
  VISIT = "visit",
  DRAFT_ANSWER = "draft_answer",
  GENERATING_REPORT = "generating_report",
  EVAL_ANSWER = "eval_answer",
  SEARCH_RESULTS = "search_results",
  WRITING_REPORT = "writing_report",
  TOOL = "tool",
}

export type ThoughtStep = {
  id?: number;
  type: ThoughtType;
  data: {
    step?: number;
    total_step?: number;
    type?: string;
    question?: string;
    answer?: string;
    urls?: string[];
    action?: string;
    thinking?: string;
    is_final?: boolean;
    final_report?: string;
    queries?: string[];
    results?: {
      url: string;
      title: string;
      description: string;
    }[];
  };
  timestamp: number;
};
