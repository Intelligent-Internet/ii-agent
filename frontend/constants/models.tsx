import { IModel } from "@/typings/agent";

// Define available models for each provider
export const PROVIDER_MODELS: { [key: string]: IModel[] } = {
  anthropic: [
    {
      model_name: "claude-sonnet-4-20250514",
      provider: "anthropic",
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
  openai: [
    {
      model_name: "gpt-4-turbo",
      provider: "openai",
    },
    {
      model_name: "gpt-4-1106-preview",
      provider: "openai",
    },
    {
      model_name: "gpt-4",
      provider: "openai",
    },
    {
      model_name: "gpt-3.5-turbo",
      provider: "openai",
    },
    {
      model_name: "gpt-4.1",
      provider: "openai",
    },
    {
      model_name: "gpt-4.1-mini",
      provider: "openai",
    },
    {
      model_name: "gpt-4.1-nano",
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
