import { useState, useEffect, useMemo } from "react";
import { X, ChevronDown, RotateCcw } from "lucide-react";
import Cookies from "js-cookie";
import { motion } from "framer-motion";

import { Button } from "./ui/button";
import { Switch } from "./ui/switch";
import { Label } from "./ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Tooltip, TooltipTrigger, TooltipContent } from "./ui/tooltip";
import { AVAILABLE_MODELS, ToolSettings } from "@/typings/agent";
import { useAppContext } from "@/context/app-context";

interface SettingsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

const SettingsDrawer = ({ isOpen, onClose }: SettingsDrawerProps) => {
  const { state, dispatch } = useAppContext();
  const [toolsExpanded, setToolsExpanded] = useState(true);
  const [reasoningExpanded, setReasoningExpanded] = useState(true);

  const isClaudeModel = useMemo(
    () => state.selectedModel?.toLowerCase().includes("claude"),
    [state.selectedModel]
  );

  const handleToolToggle = (tool: keyof ToolSettings) => {
    dispatch({
      type: "SET_TOOL_SETTINGS",
      payload: {
        ...state.toolSettings,
        [tool]: !state.toolSettings[tool],
      },
    });
  };

  const resetSettings = () => {
    dispatch({
      type: "SET_TOOL_SETTINGS",
      payload: {
        deep_research: false,
        pdf: true,
        media_generation: true,
        audio_generation: true,
        browser: true,
        thinking_tokens: 10000,
      },
    });
    dispatch({ type: "SET_SELECTED_MODEL", payload: AVAILABLE_MODELS[0] });
  };

  const handleReasoningEffortChange = (effort: string) => {
    dispatch({
      type: "SET_TOOL_SETTINGS",
      payload: {
        ...state.toolSettings,
        thinking_tokens: effort === "high" ? 10000 : 0,
      },
    });
  };

  useEffect(() => {
    if (state.selectedModel) {
      Cookies.set("selected_model", state.selectedModel, {
        expires: 365, // 1 year
        sameSite: "strict",
        secure: window.location.protocol === "https:",
      });

      // Reset thinking_tokens to 0 for non-Claude models
      if (!isClaudeModel && state.toolSettings.thinking_tokens > 0) {
        dispatch({
          type: "SET_TOOL_SETTINGS",
          payload: { ...state.toolSettings, thinking_tokens: 0 },
        });
      }
    }
  }, [state.selectedModel, isClaudeModel, state.toolSettings, dispatch]);

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 bg-black/50 z-40" onClick={onClose} />
      )}
      <motion.div
        className={`fixed top-0 right-0 h-full ${
          isOpen ? "w-[400px]" : "w-0"
        } bg-[#1e1f23] z-50 shadow-xl overflow-auto`}
        initial={{ x: "100%" }}
        animate={{ x: isOpen ? 0 : "100%" }}
        transition={{ type: "spring", damping: 30, stiffness: 300 }}
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold text-white">Run settings</h2>
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="rounded-full hover:bg-gray-700/50"
                    onClick={resetSettings}
                  >
                    <RotateCcw className="size-5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Reset Default Settings</TooltipContent>
              </Tooltip>
              <Button
                variant="ghost"
                size="icon"
                className="rounded-full hover:bg-gray-700/50"
                onClick={onClose}
              >
                <X className="size-5" />
              </Button>
            </div>
          </div>

          <div className="space-y-6">
            {/* Model selector */}
            <div className="space-y-2">
              <Select
                value={state.selectedModel}
                onValueChange={(model) =>
                  dispatch({ type: "SET_SELECTED_MODEL", payload: model })
                }
              >
                <SelectTrigger className="w-full bg-[#35363a] border-[#ffffff0f]">
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent className="bg-[#35363a] border-[#ffffff0f]">
                  {AVAILABLE_MODELS.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Reasoning Effort section - only for Claude models */}
            {isClaudeModel && (
              <div className="space-y-4 pt-4 border-t border-gray-700">
                <div
                  className="flex justify-between items-center cursor-pointer"
                  onClick={() => setReasoningExpanded(!reasoningExpanded)}
                >
                  <h3 className="text-lg font-medium text-white">
                    Reasoning Effort
                  </h3>
                  <ChevronDown
                    className={`size-5 transition-transform ${
                      reasoningExpanded ? "rotate-180" : ""
                    }`}
                  />
                </div>

                {reasoningExpanded && (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label
                        htmlFor="reasoning-effort"
                        className="text-gray-300"
                      >
                        Effort Level
                      </Label>
                      <p className="text-xs text-gray-400 mb-2">
                        Controls how much effort the model spends on reasoning
                        before responding
                      </p>
                      <Select
                        value={
                          state.toolSettings.thinking_tokens > 0
                            ? "high"
                            : "standard"
                        }
                        onValueChange={handleReasoningEffortChange}
                      >
                        <SelectTrigger className="w-full bg-[#35363a] border-[#ffffff0f]">
                          <SelectValue placeholder="Select effort level" />
                        </SelectTrigger>
                        <SelectContent className="bg-[#35363a] border-[#ffffff0f]">
                          <SelectItem value="standard">Standard</SelectItem>
                          <SelectItem value="high">High-effort</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Tools section */}
            <div className="space-y-4 pt-4 border-t border-gray-700">
              <div
                className="flex justify-between items-center cursor-pointer"
                onClick={() => setToolsExpanded(!toolsExpanded)}
              >
                <h3 className="text-lg font-medium text-white">Tools</h3>
                <ChevronDown
                  className={`size-5 transition-transform ${
                    toolsExpanded ? "rotate-180" : ""
                  }`}
                />
              </div>

              {toolsExpanded && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <Label htmlFor="deep-research" className="text-gray-300">
                        Deep Research
                      </Label>
                      <p className="text-xs text-gray-400">
                        Enable in-depth research capabilities
                      </p>
                    </div>
                    <Switch
                      id="deep-research"
                      checked={state.toolSettings.deep_research}
                      onCheckedChange={() => handleToolToggle("deep_research")}
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <Label htmlFor="pdf" className="text-gray-300">
                        PDF Processing
                      </Label>
                      <p className="text-xs text-gray-400">
                        Extract and analyze PDF documents
                      </p>
                    </div>
                    <Switch
                      id="pdf"
                      checked={state.toolSettings.pdf}
                      onCheckedChange={() => handleToolToggle("pdf")}
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <Label
                        htmlFor="media-generation"
                        className="text-gray-300"
                      >
                        Media Generation
                      </Label>
                      <p className="text-xs text-gray-400">
                        Generate images and videos
                      </p>
                    </div>
                    <Switch
                      id="media-generation"
                      checked={state.toolSettings.media_generation}
                      onCheckedChange={() =>
                        handleToolToggle("media_generation")
                      }
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <Label
                        htmlFor="audio-generation"
                        className="text-gray-300"
                      >
                        Audio Generation
                      </Label>
                      <p className="text-xs text-gray-400">
                        Generate and process audio content
                      </p>
                    </div>
                    <Switch
                      id="audio-generation"
                      checked={state.toolSettings.audio_generation}
                      onCheckedChange={() =>
                        handleToolToggle("audio_generation")
                      }
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <Label htmlFor="browser" className="text-gray-300">
                        Browser
                      </Label>
                      <p className="text-xs text-gray-400">
                        Enable web browsing capabilities
                      </p>
                    </div>
                    <Switch
                      id="browser"
                      checked={state.toolSettings.browser}
                      onCheckedChange={() => handleToolToggle("browser")}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </motion.div>
    </>
  );
};

export default SettingsDrawer;
