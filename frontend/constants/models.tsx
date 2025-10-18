import { IModel } from "@/typings/agent";

// Define available models for each provider
export const PROVIDER_MODELS: { [key: string]: IModel[] } = {
  anthropic: [
    {
      model_name: "claude-sonnet-4-20250514",
      provider: "anthropic",
    },
    {
      model_name: "claude-sonnet-4-5",
      provider: "anthropic",
      label: "Claude Sonnet 4.5",
    },
    {
      model_name: "claude-opus-4-20250514",
      provider: "anthropic",
    },
    {
      model_name: "claude-3-7-sonnet-20250219",
      provider: "anthropic",
    },
  ],
  xai: [
    {
      model_name: "grok-4-fast-reasoning",
      provider: "xai",
      label: "Grok 4 Fast (Reasoning)",
    },
    {
      model_name: "grok-3",
      provider: "xai",
      label: "Grok 3",
    },
  ],
  amazon: [
    {
      model_name: "openai.gpt-oss-120b-1:0",
      provider: "amazon",
      label: "Amazon GPT-OSS 120B",
    },
  ],
  openai: [
    {
      model_name: "gpt-5",
      provider: "openai",
    },
    {
      model_name: "gpt-4.1",
      provider: "openai",
    },
    {
      model_name: "gpt-4.5",
      provider: "openai",
    },
    {
      model_name: "o3",
      provider: "openai",
    },
    {
      model_name: "o3-mini",
      provider: "openai",
    },
    {
      model_name: "o4-mini",
      provider: "openai",
    },
    {
      model_name: "custom",
      provider: "openai",
    },
  ],
  gemini: [
    {
      model_name: "gemini-2.5-flash",
      provider: "gemini",
    },
    {
      model_name: "gemini-2.5-pro",
      provider: "gemini",
    },
  ],
  vertex: [
    {
      model_name: "claude-sonnet-4@20250514",
      provider: "anthropic",
    },
    {
      model_name: "claude-opus-4@20250514",
      provider: "anthropic",
    },
    {
      model_name: "claude-3-7-sonnet@20250219",
      provider: "anthropic",
    },
    {
      model_name: "gemini-2.5-flash",
      provider: "gemini",
    },
    {
      model_name: "gemini-2.5-pro",
      provider: "gemini",
    },
  ],
  azure: [
    {
      model_name: "gpt-4-turbo",
      provider: "openai",
    },
    {
      model_name: "gpt-4",
      provider: "openai",
    },
    {
      model_name: "gpt-4.1",
      provider: "openai",
    },
    {
      model_name: "gpt-4.5",
      provider: "openai",
    },
    {
      model_name: "o3",
      provider: "openai",
    },
    {
      model_name: "o3-mini",
      provider: "openai",
    },
    {
      model_name: "o3-pro",
      provider: "openai",
    },
    {
      model_name: "o4-mini",
      provider: "openai",
    },
  ],
};

export const getModelsForProvider = (provider: string): IModel[] => {
  return PROVIDER_MODELS[provider] ?? [];
};
