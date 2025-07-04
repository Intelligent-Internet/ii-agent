import { useState, useEffect } from "react";
import { isEmpty } from "lodash";
import Cookies from "js-cookie";
import { toast } from "sonner";
import { Pencil, Trash, Plus } from "lucide-react";
import { useAppContext } from "@/context/app-context";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { IModel, LLMConfig } from "@/typings/agent";
import { PROVIDER_MODELS } from "@/constants/models";

interface ApiKeysDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onOpen: () => void;
  initialTab?: string;
}

const isCotModels = ["o3", "o3-mini", "o3-pro", "o4-mini"];

const ApiKeysDialog = ({
  isOpen,
  onClose,
  onOpen,
  initialTab,
}: ApiKeysDialogProps) => {
  const { state, dispatch } = useAppContext();
  const [activeTab, setActiveTab] = useState(initialTab || "sandbox-config");
  const [selectedProvider, setSelectedProvider] = useState("anthropic");
  const [selectedModel, setSelectedModel] = useState<IModel>(
    PROVIDER_MODELS.anthropic[0]
  );
  const [oldSettingData, setOldSettingData] = useState<{
    llm_configs: LLMConfig[];
    search_config: {
      firecrawl_api_key: string;
      firecrawl_base_url: string;
      serpapi_api_key: string;
      tavily_api_key: string;
      jina_api_key: string;
    };
    media_config: {
      gcp_project_id: string;
      gcp_location: string;
      gcs_output_bucket: string;
      google_ai_studio_api_key: string;
    };
    audio_config: {
      openai_api_key: string;
      azure_endpoint: string;
      azure_api_version: string;
    };
    third_party_integration_config: {
      neon_db_api_key: string;
      openai_api_key: string;
      vercel_api_key: string;
    };
    sandbox_config: {
      mode: string;
      template_id: string;
      sandbox_api_key: string;
    };
  }>();
  const [customModelName, setCustomModelName] = useState("");
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<{
    modelKey: string;
    config: LLMConfig;
  } | null>(null);

  const [llmConfig, setLlmConfig] = useState<{
    [key: string]: LLMConfig;
  }>({});

  const [searchConfig, setSearchConfig] = useState({
    firecrawl_api_key: "",
    firecrawl_base_url: "",
    serpapi_api_key: "",
    tavily_api_key: "",
    jina_api_key: "",
  });

  const [mediaConfig, setMediaConfig] = useState<{
    gcp_project_id: string | undefined;
    gcp_location: string | undefined;
    gcs_output_bucket: string | undefined;
    google_ai_studio_api_key: string | undefined;
  }>({
    gcp_project_id: "",
    gcp_location: "",
    gcs_output_bucket: "",
    google_ai_studio_api_key: undefined,
  });

  const [audioConfig, setAudioConfig] = useState({
    openai_api_key: "",
    azure_endpoint: "",
    azure_api_version: "",
  });

  const [thirdPartyIntegrationConfig, setThirdPartyIntegrationConfig] =
    useState({
      neon_db_api_key: "",
      openai_api_key: "",
      vercel_api_key: "",
    });

  const [sandboxConfig, setSandboxConfig] = useState({
    mode: "local",
    template_id: "",
    sandbox_api_key: "",
  });

  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  // const [showFirecrawlBaseUrl, setShowFirecrawlBaseUrl] = useState(false); // Add state for toggle

  // Add state for media provider selection
  const [mediaProvider, setMediaProvider] = useState<"vertex" | "gemini">(
    mediaConfig.gcp_project_id ? "vertex" : "gemini"
  );

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setIsLoading(true);
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/settings`
      );

      if (!response.ok) {
        onOpen();
        return;
      }

      const data = await response.json();
      setOldSettingData(data);

      if (isEmpty(data.llm_configs)) {
        onOpen();
        return;
      }

      // Update state with fetched settings
      if (data.llm_configs) {
        setLlmConfig(data.llm_configs);

        // Set selected provider and model based on first available config
        const modelEntries: [string, LLMConfig][] = Object.entries(
          data.llm_configs
        );
        if (modelEntries.length > 0) {
          const [firstModelName, firstModelConfig] = modelEntries[0];
          const provider = firstModelConfig.api_type || "anthropic";

          setSelectedProvider(provider);
          setSelectedModel({
            model_name: firstModelName,
            provider,
          });

          // Update available models in app context
          const availableModelNames = Object.keys(data.llm_configs);
          const savedModel = Cookies.get("selected_model");
          if (savedModel && availableModelNames.includes(savedModel)) {
            dispatch({ type: "SET_SELECTED_MODEL", payload: savedModel });
          }
          dispatch({
            type: "SET_AVAILABLE_MODELS",
            payload: availableModelNames,
          });
        }
      }

      if (data.search_config) {
        setSearchConfig({
          firecrawl_api_key: data.search_config.firecrawl_api_key || undefined,
          firecrawl_base_url:
            data.search_config.firecrawl_base_url || undefined,
          serpapi_api_key: data.search_config.serpapi_api_key || undefined,
          tavily_api_key: data.search_config.tavily_api_key || undefined,
          jina_api_key: data.search_config.jina_api_key || undefined,
        });
      }

      if (data.media_config) {
        setMediaConfig({
          gcp_project_id: data.media_config.gcp_project_id || undefined,
          gcp_location: data.media_config.gcp_location || undefined,
          gcs_output_bucket: data.media_config.gcs_output_bucket || undefined,
          google_ai_studio_api_key:
            data.media_config.google_ai_studio_api_key || undefined,
        });

        // Set the media provider based on which keys are present
        if (data.media_config.gcp_project_id) {
          setMediaProvider("vertex");
        } else {
          setMediaProvider("gemini");
        }
      }

      if (data.audio_config) {
        setAudioConfig({
          openai_api_key: data.audio_config.openai_api_key || undefined,
          azure_endpoint: data.audio_config.azure_endpoint || undefined,
          azure_api_version: data.audio_config.azure_api_version || undefined,
        });
      }

      if (data.third_party_integration_config) {
        setThirdPartyIntegrationConfig({
          neon_db_api_key:
            data.third_party_integration_config.neon_db_api_key || undefined,
          openai_api_key:
            data.third_party_integration_config.openai_api_key || undefined,
          vercel_api_key:
            data.third_party_integration_config.vercel_api_key || undefined,
        });
      }

      if (data.sandbox_config) {
        setSandboxConfig({
          mode: data.sandbox_config.mode || "local",
          template_id: data.sandbox_config.template_id || undefined,
          sandbox_api_key: data.sandbox_config.sandbox_api_key || undefined,
        });
      }
    } catch (error) {
      console.error("Error fetching settings:", error);
      onOpen();
    } finally {
      setIsLoading(false);
    }
  };

  // Update selected model when provider changes
  const handleProviderChange = (provider: string) => {
    setSelectedProvider(provider);
    setSelectedModel(
      PROVIDER_MODELS[provider as keyof typeof PROVIDER_MODELS][0]
    );
    setCustomModelName(""); // Reset custom model name when provider changes
  };

  const getModelKey = (model: IModel) => {
    if (model.model_name === "custom") {
      return `custom/${customModelName}`;
    }
    return `${selectedProvider}/${model.model_name}`;
  };

  // Handle model selection
  const handleModelChange = (model: {
    model_name: string;
    provider: string;
  }) => {
    setSelectedModel(model);

    // If not custom model, ensure the model config exists
    if (model.model_name !== "custom") {
      if (!llmConfig[getModelKey(model)]) {
        setLlmConfig({
          ...llmConfig,
          [getModelKey(model)]: {
            api_key: undefined,
            base_url: undefined,
            api_type: model.provider,
            model: model.model_name,
            cot_model: isCotModels.some((m) => model.model_name?.includes(m)),
          },
        });
      } else {
        setLlmConfig({
          ...llmConfig,
          [getModelKey(model)]: {
            ...llmConfig[getModelKey(model)],
            model: model.model_name,
            cot_model: isCotModels.some((m) => model.model_name?.includes(m)),
          },
        });
      }
    } else {
      // For custom model, ensure the "custom" key exists in llmConfig
      if (!llmConfig[getModelKey(model)]) {
        setLlmConfig({
          ...llmConfig,
          [getModelKey(model)]: {
            api_key: undefined,
            base_url: undefined,
            api_type: model.provider,
            model: customModelName,
          },
        });
      }
    }
  };

  const handleSearchConfigChange = (key: string, value: string) => {
    setSearchConfig({
      ...searchConfig,
      [key]: value,
    });
  };

  const handleMediaConfigChange = (key: string, value: string) => {
    setMediaConfig({
      ...mediaConfig,
      [key]: value,
    });
  };

  const handleAudioConfigChange = (key: string, value: string) => {
    setAudioConfig({
      ...audioConfig,
      [key]: value,
    });
  };

  const handleThirdPartyIntegrationConfigChange = (
    key: string,
    value: string
  ) => {
    setThirdPartyIntegrationConfig({
      ...thirdPartyIntegrationConfig,
      [key]: value,
    });
  };

  const handleSandboxConfigChange = (key: string, value: string) => {
    setSandboxConfig({
      ...sandboxConfig,
      [key]: value,
    });
  };

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
  };

  const saveConfig = async () => {
    try {
      setIsSaving(true);

      // Combine all configs
      const configData = {
        llm_configs: llmConfig,
        search_config: searchConfig,
        media_config: mediaConfig,
        audio_config: audioConfig,
        third_party_integration_config: thirdPartyIntegrationConfig,
        sandbox_config: sandboxConfig,
      };

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/settings`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(configData),
        }
      );

      if (response.ok) {
        // Update available models in app context after saving
        const availableModelNames = Object.keys(llmConfig);
        dispatch({
          type: "SET_AVAILABLE_MODELS",
          payload: availableModelNames,
        });
        dispatch({
          type: "SET_SELECTED_MODEL",
          payload: availableModelNames[0],
        });

        toast.success("Configuration saved successfully");
        onClose();
      } else {
        throw new Error("Failed to save configuration");
      }
    } catch (error) {
      console.error("Error saving configuration:", error);
      toast.error("Failed to save configuration. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  // Function to open edit dialog for a specific config
  const handleEditConfig = (modelKey: string, config: LLMConfig) => {
    const [provider, ...rest] = modelKey.split("/");
    const modelName = rest.join("/");

    if (provider === "custom") {
      setSelectedProvider("openai");
      setCustomModelName(modelName);
      setSelectedModel({ model_name: "custom", provider: "openai" });
    } else if (provider === "vertex") {
      setSelectedProvider("vertex");
      setSelectedModel({
        model_name: modelName,
        provider:
          PROVIDER_MODELS.vertex.find((m) => m.model_name === modelName)
            ?.provider || "",
      });
    } else if (provider === "azure") {
      setSelectedProvider("azure");
      setSelectedModel({
        model_name: modelName,
        provider:
          PROVIDER_MODELS.azure.find((m) => m.model_name === modelName)
            ?.provider || "",
      });
    } else {
      setSelectedProvider(provider);
      setSelectedModel({ model_name: modelName, provider });
    }

    setEditingConfig({ modelKey, config });
    setIsEditDialogOpen(true);
  };

  // Function to delete a config
  const handleDeleteConfig = (modelKey: string) => {
    const newLlmConfig = { ...llmConfig };
    delete newLlmConfig[modelKey];
    setLlmConfig(newLlmConfig);
  };

  // Function to add a new config
  const handleAddConfig = () => {
    setSelectedProvider("anthropic");
    setSelectedModel(PROVIDER_MODELS.anthropic[0]);
    setCustomModelName("");
    // Initialize editingConfig with empty values for a new model
    setEditingConfig({
      modelKey: "",
      config: {
        api_key: undefined,
        base_url: undefined,
        api_type: "anthropic",
        model: PROVIDER_MODELS.anthropic[0].model_name,
      },
    });
    setIsEditDialogOpen(true);
  };

  const handleMediaProviderChange = (provider: "vertex" | "gemini") => {
    setMediaProvider(provider);

    // Clear fields for the non-selected provider
    if (provider === "gemini") {
      setMediaConfig({
        ...mediaConfig,
        gcp_project_id: "",
        gcp_location: "",
        gcs_output_bucket: "",
        google_ai_studio_api_key: undefined,
      });
    } else {
      setMediaConfig({
        ...mediaConfig,
        gcp_project_id: oldSettingData?.media_config.gcp_project_id || "",
        gcp_location: oldSettingData?.media_config.gcp_location || "",
        gcs_output_bucket: oldSettingData?.media_config.gcs_output_bucket || "",
        google_ai_studio_api_key: "",
      });
    }
  };

  // Function to save the edited/new config
  const handleSaveConfig = () => {
    const modelKey = getModelKey(selectedModel);

    // Create or update the config
    const updatedConfig = {
      ...llmConfig,
      [modelKey]: {
        ...(llmConfig[modelKey] || {}),
        api_key: editingConfig?.config.api_key || undefined,
        base_url: editingConfig?.config.base_url || undefined,
        api_type: selectedModel.provider,
        model:
          selectedModel.model_name === "custom"
            ? customModelName
            : selectedModel.model_name,
        cot_model: isCotModels.some((m) =>
          selectedModel.model_name?.includes(m)
        ),
        vertex_region: editingConfig?.config.vertex_region || undefined,
        vertex_project_id: editingConfig?.config.vertex_project_id || undefined,
        azure_endpoint: editingConfig?.config.azure_endpoint || undefined,
        azure_api_version: editingConfig?.config.azure_api_version || undefined,
      },
    };

    // For vertex provider, add additional fields
    if (selectedModel.provider === "vertex" && editingConfig) {
      updatedConfig[modelKey].vertex_region =
        editingConfig.config.vertex_region;
      updatedConfig[modelKey].vertex_project_id =
        editingConfig.config.vertex_project_id;
    }

    setLlmConfig(updatedConfig);
    setIsEditDialogOpen(false);
  };

  return (
    <>
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className="bg-[#1e1f23] border-[#3A3B3F] text-white sm:max-w-[700px]">
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold">
              Configuration
            </DialogTitle>
            <DialogDescription className="text-gray-400">
              Configure your LLM providers and API keys for various services.
            </DialogDescription>
          </DialogHeader>

          {isLoading ? (
            <div className="flex justify-center items-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
            </div>
          ) : (
            <>
              <Tabs value={activeTab} onValueChange={handleTabChange}>
                <TabsList className="grid grid-cols-6 mb-4 w-full">
                  <TabsTrigger value="sandbox-config">Sandbox</TabsTrigger>
                  <TabsTrigger value="llm-config">LLM</TabsTrigger>
                  <TabsTrigger value="search-config">Search</TabsTrigger>
                  <TabsTrigger value="media-config">Media</TabsTrigger>
                  <TabsTrigger value="audio-config">Audio</TabsTrigger>
                  <TabsTrigger value="third-party-config">
                    Third Party
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="sandbox-config" className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="sandbox-mode">Sandbox Mode</Label>
                    <Select
                      value={sandboxConfig.mode}
                      onValueChange={(value) =>
                        handleSandboxConfigChange("mode", value)
                      }
                    >
                      <SelectTrigger className="bg-[#35363a] border-[#ffffff0f] w-full">
                        <SelectValue placeholder="Select Sandbox Mode" />
                      </SelectTrigger>
                      <SelectContent className="bg-[#35363a] border-[#ffffff0f]">
                        <SelectItem value="local">Local</SelectItem>
                        <SelectItem value="docker">Docker</SelectItem>
                        <SelectItem value="e2b">E2B</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {sandboxConfig.mode === "e2b" && (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="template-id">Template ID</Label>
                        <Input
                          id="template-id"
                          autoComplete="off"
                          value={sandboxConfig.template_id}
                          onChange={(e) =>
                            handleSandboxConfigChange(
                              "template_id",
                              e.target.value
                            )
                          }
                          placeholder="Enter E2B Template ID"
                          className="bg-[#35363a] border-[#ffffff0f]"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="sandbox-api-key">Sandbox API Key</Label>
                        <Input
                          id="sandbox-api-key"
                          autoComplete="off"
                          type="password"
                          value={sandboxConfig.sandbox_api_key}
                          onChange={(e) =>
                            handleSandboxConfigChange(
                              "sandbox_api_key",
                              e.target.value
                            )
                          }
                          placeholder="Enter E2B API Key"
                          className="bg-[#35363a] border-[#ffffff0f]"
                        />
                      </div>
                    </>
                  )}
                </TabsContent>

                <TabsContent value="llm-config" className="space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-lg font-medium">LLM Configurations</h3>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-[#ffffff0f]"
                      onClick={handleAddConfig}
                    >
                      <Plus className="h-4 w-4 mr-1" /> Add Model
                    </Button>
                  </div>

                  {Object.entries(llmConfig).length === 0 ? (
                    <div className="text-center py-6 text-gray-400">
                      {`No LLM configurations found. Click "Add Model" to create
                      one.`}
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                      {Object.entries(llmConfig).map(([modelKey, config]) => {
                        const [provider, modelName] = modelKey.split(":");
                        const displayName =
                          modelName === "custom" ? config.model : modelName;

                        return (
                          <div
                            key={modelKey}
                            className="flex items-center justify-between p-3 bg-[#35363a] rounded-md"
                          >
                            <div className="flex-1">
                              <div className="font-medium">{displayName}</div>
                              <div className="text-xs text-white capitalize">
                                {provider}
                              </div>
                            </div>
                            <div className="flex space-x-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-8 w-8 p-0"
                                onClick={() =>
                                  handleEditConfig(modelKey, config)
                                }
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-8 w-8 p-0 text-red-500 hover:text-red-400"
                                onClick={() => handleDeleteConfig(modelKey)}
                              >
                                <Trash className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="search-config" className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="firecrawl-key">FireCrawl API Key</Label>
                      {/* <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            onClick={() =>
                              setShowFirecrawlBaseUrl(!showFirecrawlBaseUrl)
                            }
                          >
                            {showFirecrawlBaseUrl ? (
                              <ChevronUp className="h-4 w-4" />
                            ) : (
                              <ChevronDown className="h-4 w-4" />
                            )}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          {showFirecrawlBaseUrl
                            ? "Hide Base URL"
                            : "Show Base URL"}
                        </TooltipContent>
                      </Tooltip> */}
                    </div>
                    <Input
                      id="firecrawl-key"
                      type="password"
                      value={searchConfig.firecrawl_api_key}
                      onChange={(e) =>
                        handleSearchConfigChange(
                          "firecrawl_api_key",
                          e.target.value
                        )
                      }
                      placeholder="Enter FireCrawl API Key"
                      className="bg-[#35363a] border-[#ffffff0f]"
                    />
                  </div>

                  {/* {showFirecrawlBaseUrl && (
                    <div className="space-y-2">
                      <Label htmlFor="firecrawl-base-url">
                        FireCrawl Base URL
                      </Label>
                      <Input
                        id="firecrawl-base-url"
                        type="text"
                        value={searchConfig.firecrawl_base_url}
                        onChange={(e) =>
                          handleSearchConfigChange(
                            "firecrawl_base_url",
                            e.target.value
                          )
                        }
                        placeholder="Enter FireCrawl Base URL"
                        className="bg-[#35363a] border-[#ffffff0f]"
                      />
                    </div>
                  )} */}

                  <div className="space-y-2">
                    <Label htmlFor="serpapi-key">SerpAPI API Key</Label>
                    <Input
                      id="serpapi-key"
                      type="password"
                      value={searchConfig.serpapi_api_key}
                      onChange={(e) =>
                        handleSearchConfigChange(
                          "serpapi_api_key",
                          e.target.value
                        )
                      }
                      placeholder="Enter SerpAPI API Key"
                      className="bg-[#35363a] border-[#ffffff0f]"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="tavily-key">Tavily API Key</Label>
                    <Input
                      id="tavily-key"
                      type="password"
                      value={searchConfig.tavily_api_key}
                      onChange={(e) =>
                        handleSearchConfigChange(
                          "tavily_api_key",
                          e.target.value
                        )
                      }
                      placeholder="Enter Tavily API Key"
                      className="bg-[#35363a] border-[#ffffff0f]"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="jina-key">Jina API Key</Label>
                    <Input
                      id="jina-key"
                      type="password"
                      value={searchConfig.jina_api_key}
                      onChange={(e) =>
                        handleSearchConfigChange("jina_api_key", e.target.value)
                      }
                      placeholder="Enter Jina API Key"
                      className="bg-[#35363a] border-[#ffffff0f]"
                    />
                  </div>
                </TabsContent>

                <TabsContent value="media-config" className="space-y-4">
                  {state.toolSettings.media_generation ? (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="media-provider">Media Provider</Label>
                        <Select
                          value={mediaProvider}
                          onValueChange={(value) =>
                            handleMediaProviderChange(
                              value as "vertex" | "gemini"
                            )
                          }
                        >
                          <SelectTrigger className="bg-[#35363a] border-[#ffffff0f] w-full">
                            <SelectValue placeholder="Select Media Provider" />
                          </SelectTrigger>
                          <SelectContent className="bg-[#35363a] border-[#ffffff0f]">
                            <SelectItem value="gemini">
                              Google AI Studio
                            </SelectItem>
                            <SelectItem value="vertex">Vertex AI</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      {mediaProvider === "gemini" ? (
                        <div className="space-y-2">
                          <Label htmlFor="google-ai-studio-key">
                            Google AI Studio API Key
                          </Label>
                          <Input
                            id="google-ai-studio-key"
                            type="password"
                            value={mediaConfig.google_ai_studio_api_key || ""}
                            onChange={(e) =>
                              handleMediaConfigChange(
                                "google_ai_studio_api_key",
                                e.target.value
                              )
                            }
                            placeholder="Enter Google AI Studio API Key"
                            className="bg-[#35363a] border-[#ffffff0f]"
                          />
                        </div>
                      ) : (
                        <>
                          <div className="space-y-2">
                            <Label htmlFor="gcp-project-id">
                              GCP Project ID
                            </Label>
                            <Input
                              id="gcp-project-id"
                              type="text"
                              value={mediaConfig.gcp_project_id || ""}
                              onChange={(e) =>
                                handleMediaConfigChange(
                                  "gcp_project_id",
                                  e.target.value
                                )
                              }
                              placeholder="Enter Google Cloud Project ID"
                              className="bg-[#35363a] border-[#ffffff0f]"
                            />
                          </div>

                          <div className="space-y-2">
                            <Label htmlFor="gcp-location">GCP Location</Label>
                            <Input
                              id="gcp-location"
                              type="text"
                              value={mediaConfig.gcp_location || ""}
                              onChange={(e) =>
                                handleMediaConfigChange(
                                  "gcp_location",
                                  e.target.value
                                )
                              }
                              placeholder="Enter Google Cloud location/region"
                              className="bg-[#35363a] border-[#ffffff0f]"
                            />
                          </div>

                          <div className="space-y-2">
                            <Label htmlFor="gcs-output-bucket">
                              GCS Output Bucket
                            </Label>
                            <Input
                              id="gcs-output-bucket"
                              type="text"
                              value={mediaConfig.gcs_output_bucket || ""}
                              onChange={(e) =>
                                handleMediaConfigChange(
                                  "gcs_output_bucket",
                                  e.target.value
                                )
                              }
                              placeholder="Enter GCS bucket URI (e.g., gs://my-bucket-name)"
                              className="bg-[#35363a] border-[#ffffff0f]"
                            />
                          </div>
                        </>
                      )}
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-8 text-center">
                      <p className="text-gray-400">
                        Media Generation is disabled in Settings.
                      </p>
                      <p className="text-gray-500 text-sm mt-2">
                        Enable it in Settings to configure media options.
                      </p>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="audio-config" className="space-y-4">
                  {state.toolSettings.audio_generation ? (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="audio-openai-key">API Key</Label>
                        <Input
                          id="audio-openai-key"
                          type="password"
                          value={audioConfig.openai_api_key}
                          onChange={(e) =>
                            handleAudioConfigChange(
                              "openai_api_key",
                              e.target.value
                            )
                          }
                          placeholder="Enter API Key for audio services"
                          className="bg-[#35363a] border-[#ffffff0f]"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="azure-endpoint">Azure Endpoint</Label>
                        <Input
                          id="azure-endpoint"
                          type="text"
                          value={audioConfig.azure_endpoint}
                          onChange={(e) =>
                            handleAudioConfigChange(
                              "azure_endpoint",
                              e.target.value
                            )
                          }
                          placeholder="Enter Azure OpenAI endpoint"
                          className="bg-[#35363a] border-[#ffffff0f]"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="azure-api-version">
                          Azure API Version
                        </Label>
                        <Input
                          id="azure-api-version"
                          type="text"
                          value={audioConfig.azure_api_version}
                          onChange={(e) =>
                            handleAudioConfigChange(
                              "azure_api_version",
                              e.target.value
                            )
                          }
                          placeholder="Enter Azure API version"
                          className="bg-[#35363a] border-[#ffffff0f]"
                        />
                      </div>
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-8 text-center">
                      <p className="text-gray-400">
                        Audio Generation is disabled in Settings.
                      </p>
                      <p className="text-gray-500 text-sm mt-2">
                        Enable it in Settings to configure audio options.
                      </p>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="third-party-config" className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="neon-db-key">Neon DB API Key</Label>
                    <Input
                      id="neon-db-key"
                      type="password"
                      value={thirdPartyIntegrationConfig.neon_db_api_key}
                      onChange={(e) =>
                        handleThirdPartyIntegrationConfigChange(
                          "neon_db_api_key",
                          e.target.value
                        )
                      }
                      placeholder="Enter Neon DB API Key"
                      className="bg-[#35363a] border-[#ffffff0f]"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="third-party-openai-key">
                      OpenAI API Key
                    </Label>
                    <Input
                      id="third-party-openai-key"
                      type="password"
                      value={thirdPartyIntegrationConfig.openai_api_key}
                      onChange={(e) =>
                        handleThirdPartyIntegrationConfigChange(
                          "openai_api_key",
                          e.target.value
                        )
                      }
                      placeholder="Enter OpenAI API Key"
                      className="bg-[#35363a] border-[#ffffff0f]"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="vercel-key">Vercel API Key</Label>
                    <Input
                      id="vercel-key"
                      type="password"
                      value={thirdPartyIntegrationConfig.vercel_api_key}
                      onChange={(e) =>
                        handleThirdPartyIntegrationConfigChange(
                          "vercel_api_key",
                          e.target.value
                        )
                      }
                      placeholder="Enter Vercel API Key"
                      className="bg-[#35363a] border-[#ffffff0f]"
                    />
                  </div>
                </TabsContent>
              </Tabs>

              <DialogFooter className="mt-6">
                <Button
                  variant="outline"
                  onClick={onClose}
                  className="border-[#ffffff0f] h-10"
                >
                  Cancel
                </Button>
                <Button
                  onClick={saveConfig}
                  className="bg-gradient-skyblue-lavender"
                  disabled={isSaving}
                >
                  {isSaving ? "Saving..." : "Save Configuration"}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit/Add Model Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="bg-[#1e1f23] border-[#3A3B3F] text-white sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold">
              {editingConfig
                ? "Edit Model Configuration"
                : "Add Model Configuration"}
            </DialogTitle>
            <DialogDescription className="text-gray-400">
              Configure your LLM provider and API settings.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="llm-provider">LLM Provider</Label>
              <Select
                value={selectedProvider}
                onValueChange={handleProviderChange}
              >
                <SelectTrigger className="bg-[#35363a] border-[#ffffff0f] w-full">
                  <SelectValue placeholder="Select LLM Provider" />
                </SelectTrigger>
                <SelectContent className="bg-[#35363a] border-[#ffffff0f]">
                  <SelectItem value="anthropic">Anthropic</SelectItem>
                  <SelectItem value="openai">OpenAI</SelectItem>
                  <SelectItem value="gemini">Gemini</SelectItem>
                  <SelectItem value="vertex">Vertex AI</SelectItem>
                  <SelectItem value="azure">Azure</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {selectedProvider && (
              <div className="space-y-2">
                <Label htmlFor="model-name">Model Name</Label>
                <Select
                  value={selectedModel.model_name}
                  onValueChange={(value) =>
                    handleModelChange({
                      model_name: value,
                      provider: selectedModel.provider,
                    })
                  }
                >
                  <SelectTrigger className="bg-[#35363a] border-[#ffffff0f] w-full">
                    <SelectValue placeholder="Select Model" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#35363a] border-[#ffffff0f]">
                    {PROVIDER_MODELS[
                      selectedProvider as keyof typeof PROVIDER_MODELS
                    ].map((model) => (
                      <SelectItem
                        key={model.model_name}
                        value={model.model_name}
                      >
                        {model.model_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Show custom model input field when "custom" is selected */}
            {selectedModel.model_name === "custom" && (
              <div className="space-y-2">
                <Label htmlFor="custom-model-name">Custom Model Name</Label>
                <Input
                  id="custom-model-name"
                  type="text"
                  value={customModelName}
                  onChange={(e) => setCustomModelName(e.target.value)}
                  placeholder="Enter custom model name"
                  className="bg-[#35363a] border-[#ffffff0f]"
                />
              </div>
            )}

            {/* Provider-specific fields */}
            {selectedProvider === "anthropic" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="api-key">API Key</Label>
                  <Input
                    id="api-key"
                    type="password"
                    value={editingConfig?.config.api_key || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            api_key: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter API Key"
                    className="bg-[#35363a] border-[#ffffff0f]"
                  />
                </div>
              </div>
            )}

            {selectedProvider === "openai" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="api-key">API Key</Label>
                  <Input
                    id="api-key"
                    type="password"
                    value={editingConfig?.config.api_key || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            api_key: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter API Key"
                    className="bg-[#35363a] border-[#ffffff0f]"
                    disabled={
                      selectedModel.model_name === "custom" &&
                      !customModelName.trim()
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="base-url">Base URL (Optional)</Label>
                  <Input
                    id="base-url"
                    type="text"
                    value={editingConfig?.config.base_url || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            base_url: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter Base URL (if using a proxy)"
                    className="bg-[#35363a] border-[#ffffff0f]"
                    disabled={
                      selectedModel.model_name === "custom" &&
                      !customModelName.trim()
                    }
                  />
                </div>
              </div>
            )}

            {selectedProvider === "gemini" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="api-key">API Key</Label>
                  <Input
                    id="api-key"
                    type="password"
                    value={editingConfig?.config.api_key || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            api_key: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter Gemini API Key"
                    className="bg-[#35363a] border-[#ffffff0f]"
                  />
                </div>
              </div>
            )}

            {selectedProvider === "vertex" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="vertex-project-id">Project ID</Label>
                  <Input
                    id="vertex-project-id"
                    type="text"
                    value={editingConfig?.config.vertex_project_id || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            vertex_project_id: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter Google Cloud Project ID"
                    className="bg-[#35363a] border-[#ffffff0f]"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="vertex-region">Region</Label>
                  <Input
                    id="vertex-region"
                    type="text"
                    value={editingConfig?.config.vertex_region || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            vertex_region: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter Vertex AI Region (e.g., us-central1)"
                    className="bg-[#35363a] border-[#ffffff0f]"
                  />
                </div>
              </div>
            )}

            {selectedProvider === "azure" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="azure-endpoint">Azure Endpoint</Label>
                  <Input
                    id="azure-endpoint"
                    type="text"
                    value={editingConfig?.config.azure_endpoint || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            azure_endpoint: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter Azure OpenAI endpoint"
                    className="bg-[#35363a] border-[#ffffff0f]"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="api-key">API Key</Label>
                  <Input
                    id="api-key"
                    type="password"
                    value={editingConfig?.config.api_key || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            api_key: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter API Key"
                    className="bg-[#35363a] border-[#ffffff0f]"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="azure-api-version">Azure API Version</Label>
                  <Input
                    id="azure-api-version"
                    type="text"
                    value={editingConfig?.config.azure_api_version || ""}
                    onChange={(e) => {
                      if (editingConfig) {
                        setEditingConfig({
                          ...editingConfig,
                          config: {
                            ...editingConfig.config,
                            azure_api_version: e.target.value,
                          },
                        });
                      }
                    }}
                    placeholder="Enter Azure API version"
                    className="bg-[#35363a] border-[#ffffff0f]"
                  />
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsEditDialogOpen(false)}
              className="border-[#ffffff0f] h-10"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSaveConfig}
              className="bg-gradient-skyblue-lavender"
              disabled={
                selectedModel.model_name === "custom" && !customModelName.trim()
              }
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default ApiKeysDialog;
