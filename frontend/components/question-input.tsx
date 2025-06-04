import { motion } from "framer-motion";
import {
  ArrowUp,
  Loader2,
  Paperclip,
  Settings2,
  Plus,
  Folder,
} from "lucide-react";
import { useState, useEffect, useRef, useCallback } from "react";
import Image from "next/image";
import { toast } from "sonner";
import Cookies from "js-cookie";

import SettingsDrawer from "./settings-drawer";
import { getFileIconAndColor } from "@/utils/file-utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { GoogleDocument, GooglePickerResponse } from "@/typings/agent";
import { useGoogleDrive } from "@/hooks/use-google-drive";
import { useAppContext } from "@/context/app-context";
import { useUploadFiles } from "@/hooks/use-upload-files";

interface FileUploadStatus {
  name: string;
  loading: boolean;
  error?: string;
  preview?: string;
  isImage: boolean;
  googleDriveId?: string;
  isFolder?: boolean;
  fileCount?: number;
}

interface QuestionInputProps {
  hideSettings?: boolean;
  className?: string;
  textareaClassName?: string;
  placeholder?: string;
  value: string;
  setValue: (value: string) => void;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (question: string) => void;
  isDisabled?: boolean;
  handleEnhancePrompt?: () => void;
  handleCancel?: () => void;
}

const QuestionInput = ({
  hideSettings,
  className,
  textareaClassName,
  placeholder,
  value,
  setValue,
  handleKeyDown,
  handleSubmit,
  isDisabled,
  handleEnhancePrompt,
  handleCancel,
}: QuestionInputProps) => {
  const { state } = useAppContext();
  const [files, setFiles] = useState<FileUploadStatus[]>([]);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isGDriveAuthLoading, setIsGDriveAuthLoading] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { handleFileUpload } = useUploadFiles();

  const {
    isGoogleDriveConnected,
    googlePickerApiLoaded,
    handleGoogleDriveAuth,
    setIsGoogleDriveConnected,
  } = useGoogleDrive();

  // Handle key down events with auto-scroll for Shift+Enter
  const handleKeyDownWithAutoScroll = (
    e: React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    if (e.key === "Enter") {
      if (e.shiftKey) {
        // Check if cursor is at the last line before allowing default behavior
        const textarea = textareaRef.current;
        if (textarea) {
          const cursorPosition = textarea.selectionStart;
          const text = textarea.value;

          // Check if cursor is at or near the end of the text
          const isAtLastLine = !text.substring(cursorPosition).includes("\n");

          // Allow default behavior for Shift+Enter (new line)
          // Only schedule auto-scroll if we're at the last line
          if (isAtLastLine) {
            setTimeout(() => {
              if (textarea) {
                textarea.scrollTop = textarea.scrollHeight;
              }
            }, 0);
          }
        }
      } else {
        // Original behavior for Enter key
        handleKeyDown(e);
      }
    } else {
      // Pass other key events to the original handler
      handleKeyDown(e);
    }
  };

  // Clean up object URLs when component unmounts
  useEffect(() => {
    return () => {
      files.forEach((file) => {
        if (file.preview) URL.revokeObjectURL(file.preview);
      });
    };
  }, [files]);

  const isImageFile = useCallback((fileName: string): boolean => {
    const ext = fileName.split(".").pop()?.toLowerCase() || "";
    return ["jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "svg"].includes(
      ext
    );
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || !handleFileUpload) return;

    // Create file status objects
    const newFiles = Array.from(e.target.files).map((file) => {
      const isImage = isImageFile(file.name);
      const preview = isImage ? URL.createObjectURL(file) : undefined;

      return {
        name: file.name,
        loading: true,
        isImage,
        preview,
      };
    });

    setFiles((prev) => [...prev, ...newFiles]);

    // Call the parent handler
    handleFileUpload(e);

    // After a delay, mark files as not loading (this would ideally be handled by the parent)
    setTimeout(() => {
      setFiles((prev) => prev.map((file) => ({ ...file, loading: false })));
    }, 5000);
  };

  const pickerCallback = useCallback(
    async (data: GooglePickerResponse) => {
      if (data.action === window.google.picker.Action.CANCEL) {
        return;
      }

      if (data.action === window.google.picker.Action.PICKED) {
        if (!data.docs || data.docs.length === 0) {
          return;
        }

        // Process each selected item (file or folder)
        for (const doc of data.docs) {
          if (doc.mimeType === "application/vnd.google-apps.folder") {
            // Handle folder selection
            try {
              // Add folder to UI immediately
              const folderFile: FileUploadStatus = {
                name: doc.name,
                loading: true,
                isImage: false,
                isFolder: true,
                googleDriveId: doc.id,
              };

              setFiles((prev) => [...prev, folderFile]);

              // Fetch folder contents from our backend
              const response = await fetch(`/api/google/folders/${doc.id}`);
              if (!response.ok) {
                throw new Error(
                  `Failed to fetch folder contents: ${response.statusText}`
                );
              }
              const folderContents = await response.json();

              // Filter out shortcuts and subfolders
              const processableFiles = folderContents.files.filter(
                (file: GoogleDocument) =>
                  file.mimeType !== "application/vnd.google-apps.shortcut" &&
                  file.mimeType !== "application/vnd.google-apps.folder"
              );

              // Update folder with file count
              const fileCount = processableFiles.length;
              setFiles((prev) =>
                prev.map((f) =>
                  f.googleDriveId === doc.id && f.isFolder
                    ? { ...f, fileCount }
                    : f
                )
              );

              // Create a special "folder file" to represent the folder in messages
              const folderMetadataFile = new File(
                [JSON.stringify({ type: "folder", name: doc.name, fileCount })],
                `folder:${doc.name}:${fileCount}`,
                { type: "application/json" }
              );

              // Add this folder metadata file to the upload
              const folderMetadataFileList = {
                length: 1,
                item: () => folderMetadataFile,
                [Symbol.iterator]: function* () {
                  yield folderMetadataFile;
                },
              } as FileList;

              const folderMetadataEvent = {
                target: {
                  files: folderMetadataFileList,
                },
              } as React.ChangeEvent<HTMLInputElement>;

              if (handleFileUpload) {
                handleFileUpload(folderMetadataEvent);
              }

              // Process each file in the folder (in the background)
              for (const file of processableFiles) {
                try {
                  const fileResponse = await fetch(
                    `/api/google/files/${file.id}`
                  );
                  if (!fileResponse.ok) {
                    throw new Error(
                      `Failed to fetch file: ${fileResponse.statusText}`
                    );
                  }
                  const fileData = await fileResponse.json();

                  // Convert base64 data to a Blob
                  let blob;
                  if (fileData.content.startsWith("data:")) {
                    const base64Response = await fetch(fileData.content);
                    blob = await base64Response.blob();
                  } else {
                    blob = new Blob([fileData.content], {
                      type: fileData.mimeType || "text/plain",
                    });
                  }

                  // Create a File object
                  const fileObj = new File([blob], file.name, {
                    type: fileData.mimeType,
                  });

                  // Create a synthetic file list with this file
                  const fileList = {
                    length: 1,
                    item: () => fileObj,
                    [Symbol.iterator]: function* () {
                      yield fileObj;
                    },
                  } as FileList;

                  // Create and dispatch synthetic event
                  const syntheticEvent = {
                    target: {
                      files: fileList,
                    },
                  } as React.ChangeEvent<HTMLInputElement>;

                  if (handleFileUpload) {
                    handleFileUpload(syntheticEvent, true);
                  }
                } catch (error) {
                  console.error(`Error processing file ${file.name}:`, error);
                }
              }

              // Mark folder as done loading
              setFiles((prev) =>
                prev.map((f) =>
                  f.googleDriveId === doc.id && f.isFolder
                    ? { ...f, loading: false }
                    : f
                )
              );
            } catch {
              toast.error(`Failed to process folder: ${doc.name}`);
              // Remove the folder from UI on error
              setFiles((prev) =>
                prev.filter((f) => !(f.googleDriveId === doc.id && f.isFolder))
              );
            }
          } else {
            // Handle single file selection (existing code)
            const isImage = isImageFile(doc.name);
            const newFile = {
              name: doc.name,
              loading: true,
              isImage,
              googleDriveId: doc.id,
            };

            setFiles((prev) => [...prev, newFile]);

            try {
              const response = await fetch(`/api/google/files/${doc.id}`);
              if (!response.ok) {
                throw new Error(`Failed to fetch file: ${response.statusText}`);
              }
              const fileData = await response.json();
              setFiles((prev) =>
                prev.map((file) =>
                  file.googleDriveId === doc.id
                    ? { ...file, preview: fileData.content }
                    : file
                )
              );

              let blob;
              if (fileData.content.startsWith("data:")) {
                const base64Response = await fetch(fileData.content);
                blob = await base64Response.blob();
              } else {
                blob = new Blob([fileData.content], {
                  type: fileData.mimeType || "text/plain",
                });
              }

              const file = new File([blob], doc.name, {
                type: fileData.mimeType,
              });
              const fileList = {
                length: 1,
                item: () => file,
                [Symbol.iterator]: function* () {
                  yield file;
                },
              } as FileList;

              const syntheticEvent = {
                target: {
                  files: fileList,
                },
              } as React.ChangeEvent<HTMLInputElement>;

              if (handleFileUpload) {
                handleFileUpload(syntheticEvent);
              }
            } catch {
              toast.error("Failed to process file from Google Drive");
            } finally {
              setFiles((prev) =>
                prev.map((file) =>
                  file.googleDriveId === doc.id
                    ? {
                        ...file,
                        loading: false,
                      }
                    : file
                )
              );
            }
          }
        }
      }
    },
    [handleFileUpload, isImageFile]
  );

  const handleGoogleDriveSelect = useCallback(async () => {
    Cookies.remove("open_google_picker");
    if (!isGoogleDriveConnected) {
      const success = await handleGoogleDriveAuth();
      if (!success) return;
    }

    if (!googlePickerApiLoaded) {
      toast.error(
        "Google Picker API is still loading. Please try again in a moment."
      );
      return;
    }

    try {
      // Get picker token from our backend
      const response = await fetch("/api/google/picker-token");

      if (!response.ok) {
        if (response.status === 401) {
          setIsGoogleDriveConnected(false);
          toast.error("Google Drive authentication expired. Please reconnect.");
          return;
        }
        throw new Error("Failed to get Google Picker token");
      }

      const { accessToken, developerKey, appId } = await response.json();

      // Create and render a Picker object
      const picker = new window.google.picker.PickerBuilder()
        .addView(
          new window.google.picker.DocsView()
            .setIncludeFolders(true)
            .setSelectFolderEnabled(true)
        )
        .setOAuthToken(accessToken)
        .setDeveloperKey(developerKey)
        .setAppId(appId)
        .setCallback(pickerCallback)
        .enableFeature(window.google.picker.Feature.MULTISELECT_ENABLED)
        .build();

      picker.setVisible(true);
    } catch (error) {
      console.error("Error creating Google Picker:", error);
      toast.error("Failed to open Google Drive picker");
    }
  }, [
    googlePickerApiLoaded,
    handleGoogleDriveAuth,
    isGoogleDriveConnected,
    pickerCallback,
    setIsGoogleDriveConnected,
  ]);

  const handleGoogleDriveClick = async () => {
    if (!handleGoogleDriveAuth || !handleGoogleDriveSelect) return;

    setIsGDriveAuthLoading(true);
    try {
      if (!isGoogleDriveConnected) {
        Cookies.set("open_google_picker", "true", { expires: 1 });
        await handleGoogleDriveAuth();
      } else {
        handleGoogleDriveSelect();
      }
    } catch (error) {
      console.error("Google Drive auth error:", error);
    } finally {
      setIsGDriveAuthLoading(false);
    }
  };

  useEffect(() => {
    const openPicker = Cookies.get("open_google_picker") === "true";
    if (isGoogleDriveConnected && openPicker) {
      setTimeout(() => {
        handleGoogleDriveSelect();
      }, 500);
    }
  }, [isGoogleDriveConnected]);

  // const removeFile = (fileName: string) => {
  //   setFiles((prev) => {
  //     // Find the file to remove
  //     const fileToRemove = prev.find((file) => file.name === fileName);

  //     // Revoke object URL if it exists
  //     if (fileToRemove?.preview) {
  //       URL.revokeObjectURL(fileToRemove.preview);
  //     }

  //     // Filter out the file
  //     return prev.filter((file) => file.name !== fileName);
  //   });
  // };

  return (
    <motion.div
      key="input-view"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, y: -10 }}
      transition={{
        type: "spring",
        stiffness: 300,
        damping: 30,
        mass: 1,
      }}
      className={`w-full max-w-2xl z-50 ${className}`}
    >
      {!hideSettings && (
        <SettingsDrawer
          isOpen={isSettingsOpen}
          onClose={() => setIsSettingsOpen(false)}
        />
      )}

      <motion.div
        className="relative rounded-xl"
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1 }}
      >
        {files.length > 0 && (
          <div className="absolute top-4 left-4 right-2 flex items-center overflow-auto gap-2 z-10">
            {files.map((file) => {
              if (file.isImage && file.preview) {
                return (
                  <div key={file.name} className="relative">
                    <div className="w-20 h-20 rounded-xl overflow-hidden">
                      <img
                        src={file.preview}
                        alt={file.name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    {/* <button
                      onClick={() => removeFile(file.name)}
                      className="absolute -top-2 -right-2 bg-black rounded-full p-1 hover:bg-gray-700"
                    >
                      <X className="size-4 text-white" />
                    </button> */}
                    {(state.isUploading || file.loading) && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/30 rounded-xl">
                        <Loader2 className="size-5 text-white animate-spin" />
                      </div>
                    )}
                  </div>
                );
              }

              if (file.isFolder) {
                return (
                  <div
                    key={file.name}
                    className="flex items-center gap-2 bg-neutral-900 text-white rounded-full px-3 py-2 border border-gray-700 shadow-sm"
                  >
                    <div className="flex items-center justify-center w-10 h-10 bg-blue-600 rounded-full">
                      {state.isUploading || file.loading ? (
                        <Loader2 className="size-5 text-white animate-spin" />
                      ) : (
                        <Folder className="size-5 text-white" />
                      )}
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium truncate max-w-[200px]">
                        {file.name}
                      </span>
                      <span className="text-xs text-gray-500">
                        {file.fileCount
                          ? `${file.fileCount} ${
                              file.fileCount === 1 ? "file" : "files"
                            }`
                          : "Folder"}
                      </span>
                    </div>
                  </div>
                );
              }

              const { IconComponent, bgColor, label } = getFileIconAndColor(
                file.name
              );

              return (
                <div
                  key={file.name}
                  className="flex items-center gap-2 bg-neutral-900 text-white rounded-full px-3 py-2 border border-gray-700 shadow-sm"
                >
                  <div
                    className={`flex items-center justify-center w-10 h-10 ${bgColor} rounded-full`}
                  >
                    {state.isUploading || file.loading ? (
                      <Loader2 className="size-5 text-white animate-spin" />
                    ) : (
                      <IconComponent className="size-5 text-white" />
                    )}
                  </div>
                  <div className="flex flex-col">
                    <span className="text-sm font-medium truncate max-w-[200px]">
                      {file.name}
                    </span>
                    <span className="text-xs text-gray-500">{label}</span>
                  </div>
                  {/* <button
                    onClick={() => removeFile(file.name)}
                    className="ml-2 rounded-full p-1 hover:bg-gray-700"
                  >
                    <X className="size-4" />
                  </button> */}
                </div>
              );
            })}
          </div>
        )}
        <Textarea
          className={`w-full p-4 pb-[72px] rounded-xl !text-lg focus:ring-0 resize-none !placeholder-gray-400 !bg-[#35363a] border-[#ffffff0f] shadow-[0px_0px_10px_0px_rgba(0,0,0,0.02)] ${
            files.length > 0 ? "pt-24 h-60" : "h-50"
          } ${textareaClassName}`}
          placeholder={
            placeholder ||
            "Enter your research query or complex question for in-depth analysis..."
          }
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDownWithAutoScroll}
          ref={textareaRef}
        />
        <div className="flex justify-between items-center absolute bottom-0 py-4 m-px w-[calc(100%-4px)] rounded-b-xl bg-[#35363a] px-4">
          <div className="flex items-center gap-x-3">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="hover:bg-gray-700/50 size-10 rounded-full cursor-pointer border border-[#ffffff0f] shadow-sm"
                  disabled={
                    state.isUploading ||
                    state.isLoading ||
                    isDisabled ||
                    files.some((f) => f.loading)
                  }
                >
                  <Plus className="size-6 text-gray-400" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                className="bg-neutral-900 border-gray-700 text-white"
              >
                <DropdownMenuItem
                  className="flex p-2 items-center gap-2 cursor-pointer hover:bg-gray-800"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Paperclip className="size-5" />
                  <span>Add images and files</span>
                </DropdownMenuItem>

                <DropdownMenuItem
                  className="flex p-2 items-center gap-2 cursor-pointer hover:bg-gray-800"
                  onClick={handleGoogleDriveClick}
                  disabled={isGDriveAuthLoading}
                >
                  {isGDriveAuthLoading ? (
                    <Loader2 className="size-5 text-gray-400 animate-spin" />
                  ) : (
                    <Image
                      src="/icons/google-drive.svg"
                      alt="Google Drive"
                      width={20}
                      height={20}
                    />
                  )}
                  <span>
                    {isGoogleDriveConnected
                      ? "Add from Google Drive"
                      : "Connect with Google Drive"}
                  </span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {!hideSettings && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="hover:bg-gray-700/50 size-10 rounded-full cursor-pointer border border-[#ffffff0f] shadow-sm"
                    onClick={() => setIsSettingsOpen(true)}
                    disabled={state.isLoading}
                  >
                    <Settings2 className="size-5 text-gray-400" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Settings</TooltipContent>
              </Tooltip>
            )}
            <input
              ref={fileInputRef}
              id="file-upload"
              type="file"
              multiple
              className="hidden"
              onChange={handleFileChange}
              disabled={state.isUploading || state.isLoading}
            />
          </div>

          <div className="flex items-center gap-x-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="hover:bg-gray-700/50 size-10 rounded-full cursor-pointer border border-[#ffffff0f] shadow-sm"
                  onClick={handleEnhancePrompt}
                  disabled={
                    state.isGeneratingPrompt ||
                    !value.trim() ||
                    isDisabled ||
                    state.isLoading ||
                    state.isUploading
                  }
                >
                  {state.isGeneratingPrompt ? (
                    <Loader2 className="size-5 text-gray-400 animate-spin" />
                  ) : (
                    <Image
                      src="/icons/AI.svg"
                      alt="Logo"
                      width={24}
                      height={24}
                    />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>Enhance Prompt</TooltipContent>
            </Tooltip>
            {state.isLoading && handleCancel ? (
              <Button
                onClick={handleCancel}
                className="cursor-pointer size-10 font-bold p-0 !bg-black rounded-full hover:scale-105 active:scale-95 transition-transform shadow-[0_4px_10px_rgba(0,0,0,0.2)]"
              >
                <div className="size-3 rounded-xs bg-white" />
              </Button>
            ) : (
              <Button
                disabled={
                  !value.trim() ||
                  isDisabled ||
                  state.isLoading ||
                  state.isUploading
                }
                onClick={() => handleSubmit(value)}
                className="cursor-pointer !border !border-red p-4 size-10 font-bold bg-gradient-skyblue-lavender rounded-full hover:scale-105 active:scale-95 transition-transform shadow-[0_4px_10px_rgba(0,0,0,0.2)]"
              >
                <ArrowUp className="size-5" />
              </Button>
            )}
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default QuestionInput;
