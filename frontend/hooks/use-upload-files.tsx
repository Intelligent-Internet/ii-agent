import { toast } from "sonner";
import { useCallback } from "react";

import { useAppContext } from "@/context/app-context";
import { Message } from "@/typings/agent";

interface UploadResult {
  name: string;
  success: boolean;
}

export function useUploadFiles() {
  const { state, dispatch } = useAppContext();

  const uploadFiles = useCallback(
    async (
      files: File[],
      connectionId: string | undefined,
      dontAddToUserMessage?: boolean
    ): Promise<UploadResult[]> => {
      if (!files.length) return [];

      // Check if we're dealing with a folder upload from Google Drive
      const folderFile = files.find((file) => file.name.startsWith("folder:"));

      dispatch({ type: "SET_IS_UPLOADING", payload: true });

      // Create a map of filename to content for message history
      const fileContentMap: { [filename: string]: string } = {};

      // If this is a folder upload, only include the folder metadata in the message
      const messageFiles = folderFile
        ? [folderFile.name]
        : files.map((file) => file.name);

      // Add files to message history (initially without content)
      const newUserMessage: Message = {
        id: Date.now().toString(),
        role: "user",
        files: messageFiles,
        fileContents: fileContentMap,
        timestamp: Date.now(),
      };

      if (!dontAddToUserMessage) {
        dispatch({
          type: "ADD_MESSAGE",
          payload: newUserMessage,
        });
      }

      // Process each file in parallel
      const uploadPromises = files.map(async (file) => {
        return new Promise<UploadResult>(async (resolve) => {
          try {
            const reader = new FileReader();

            reader.onload = async (e) => {
              const content = e.target?.result as string;
              fileContentMap[file.name] = content;

              // Upload the file
              const response = await fetch(
                `${process.env.NEXT_PUBLIC_API_URL}/api/upload`,
                {
                  method: "POST",
                  headers: {
                    "Content-Type": "application/json",
                  },
                  body: JSON.stringify({
                    session_id: connectionId,
                    file: {
                      path: file.name,
                      content,
                    },
                  }),
                }
              );

              const result = await response.json();

              if (response.ok) {
                // Update uploaded files state
                dispatch({
                  type: "ADD_UPLOADED_FILES",
                  payload: [result.file.path],
                });
                resolve({ name: file.name, success: true });
              } else {
                console.error(`Error uploading ${file.name}:`, result.error);
                resolve({ name: file.name, success: false });
              }
            };

            reader.onerror = () => {
              resolve({ name: file.name, success: false });
            };

            // Read as data URL
            reader.readAsDataURL(file);
          } catch (error) {
            console.error(`Error processing ${file.name}:`, error);
            resolve({ name: file.name, success: false });
          }
        });
      });

      try {
        // Wait for all uploads to complete
        const results = await Promise.all(uploadPromises);

        // Check if any uploads failed
        const failedUploads = results.filter((r) => !r.success);
        if (failedUploads.length > 0) {
          toast.error(`Failed to upload ${failedUploads.length} file(s)`);
        }

        // Update message with final content
        dispatch({
          type: "UPDATE_MESSAGE",
          payload: {
            ...newUserMessage,
            fileContents: folderFile
              ? { [folderFile.name]: fileContentMap[folderFile.name] }
              : fileContentMap,
          },
        });

        return results;
      } catch (error) {
        console.error("Error uploading files:", error);
        toast.error("Error uploading files");
        return [];
      } finally {
        dispatch({ type: "SET_IS_UPLOADING", payload: false });
      }
    },
    [state.uploadedFiles, dispatch]
  );

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
    dontAddToUserMessage?: boolean
  ) => {
    if (!event.target.files || event.target.files.length === 0) return;

    const files = Array.from(event.target.files);
    const workspacePath = state.workspaceInfo || "";
    const connectionId = workspacePath.split("/").pop();

    await uploadFiles(files, connectionId, dontAddToUserMessage);

    // Clear the input
    event.target.value = "";
  };

  return { handleFileUpload, uploadFiles };
}
