"use client";

import type { editor } from "monaco-editor";
import { Editor, Monaco } from "@monaco-editor/react";
import {
  ChevronDown,
  ChevronRight,
  File,
  Folder,
  ChevronRight as ChevronRightIcon,
} from "lucide-react";
import { useRef, useState, useEffect } from "react";

export const ROOT_PATH = process.env.NEXT_PUBLIC_WORKSPACE_PATH || "/";
const ROOT_NAME = "ii-agent";

// Map file extensions to Monaco editor language IDs
const languageMap: { [key: string]: string } = {
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  json: "json",
  md: "markdown",
  css: "css",
  scss: "scss",
  less: "less",
  html: "html",
  xml: "xml",
  yaml: "yaml",
  yml: "yaml",
  py: "python",
  rb: "ruby",
  php: "php",
  java: "java",
  cpp: "cpp",
  c: "c",
  cs: "csharp",
  go: "go",
  rs: "rust",
  swift: "swift",
  kt: "kotlin",
  sql: "sql",
  sh: "shell",
  bash: "shell",
  dockerfile: "dockerfile",
  vue: "vue",
  svelte: "svelte",
  graphql: "graphql",
  env: "plaintext",
};

interface FileStructure {
  name: string;
  type: "file" | "folder";
  children?: FileStructure[];
  language?: string;
  value?: string;
  path: string;
}

interface CodeEditorProps {
  className?: string;
  activeFile?: string;
  setActiveFile?: (file: string) => void;
}

const CodeEditor = ({
  className,
  activeFile,
  setActiveFile,
}: CodeEditorProps) => {
  const [activeLanguage, setActiveLanguage] = useState<string>("plaintext");
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set()
  );
  const [fileStructure, setFileStructure] = useState<FileStructure[]>([]);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const [fileContent, setFileContent] = useState<string>("");

  const getFileLanguage = (fileName: string): string => {
    const extension = fileName.split(".").pop()?.toLowerCase() || "";
    // Handle special case for files like "Dockerfile"
    if (fileName.toLowerCase() === "dockerfile") {
      return languageMap["dockerfile"];
    }
    return languageMap[extension] || "plaintext";
  };

  const loadDirectory = async (path: string) => {
    try {
      const response = await fetch("/api/files", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ path }),
      });

      if (!response.ok) {
        throw new Error("Failed to load directory");
      }

      const data = await response.json();
      setFileStructure(data.files);
      setExpandedFolders(new Set([path]));
    } catch (error) {
      console.error("Error loading directory:", error);
    }
  };

  const loadFileContent = async (filePath: string) => {
    try {
      const response = await fetch("/api/files/content", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ path: filePath }),
      });

      if (!response.ok) {
        throw new Error("Failed to load file content");
      }

      const data = await response.json();
      return data.content;
    } catch (error) {
      console.error("Error loading file:", error);
      return "";
    }
  };

  useEffect(() => {
    loadDirectory(ROOT_PATH);
  }, [activeFile]);

  const toggleFolder = (folderPath: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(folderPath)) {
        next.delete(folderPath);
      } else {
        next.add(folderPath);
      }
      return next;
    });
  };

  const renderBreadcrumb = () => {
    if (!activeFile) return null;

    const relativePath = activeFile.replace(ROOT_PATH, "");
    const parts = relativePath.split("/").filter(Boolean);
    const fileName = parts[parts.length - 1];
    const folderName = ROOT_NAME;

    return (
      <div className="flex items-center gap-2 px-2 py-1 text-sm text-neutral-400 border-b border-neutral-700">
        <span className="text-neutral-400">{folderName}</span>
        <ChevronRightIcon className="h-4 w-4" />
        <span className="text-white">{fileName}</span>
      </div>
    );
  };

  useEffect(() => {
    (async () => {
      if (activeFile) {
        setActiveLanguage(getFileLanguage(activeFile));
        const content = await loadFileContent(activeFile);
        setFileContent(content);
      }
    })();
  }, [activeFile]);

  const renderFileTree = (items: FileStructure[]) => {
    // Sort items: folders first, then files, both in alphabetical order
    const sortedItems = [...items].sort((a, b) => {
      if (a.type === b.type) {
        // If both are folders or both are files, sort alphabetically
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
      }
      // Folders come before files
      return a.type === "folder" ? -1 : 1;
    });

    return sortedItems.map((item) => {
      const fullPath = item.path;

      if (item.type === "folder") {
        const isExpanded = expandedFolders.has(fullPath);
        return (
          <div key={fullPath}>
            <button
              className="flex items-center gap-2 w-full px-2 py-1 hover:bg-neutral-700 text-left text-sm"
              onClick={() => toggleFolder(fullPath)}
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
              <Folder className="h-4 w-4" />
              {item.name}
            </button>
            {isExpanded && item.children && (
              <div className="ml-4">{renderFileTree(item.children)}</div>
            )}
          </div>
        );
      }

      return (
        <button
          key={fullPath}
          className={`flex items-center gap-2 w-full px-2 py-1 hover:bg-neutral-700 text-left text-sm ${
            activeFile === fullPath
              ? "bg-neutral-700 text-white"
              : "text-neutral-400"
          }`}
          onClick={() => {
            setActiveFile?.(fullPath);
          }}
        >
          <File className="h-4 w-4" />
          {item.name}
        </button>
      );
    });
  };

  return (
    <div
      className={`flex flex-col h-[calc(100vh-156px)] rounded-xl ${className}`}
    >
      <div className="flex flex-1 h-full">
        {/* File Explorer */}
        <div className="w-64 bg-neutral-900 border-r border-neutral-700 flex flex-col">
          <div className="px-2 py-1 text-sm font-medium text-neutral-400 border-b border-neutral-700">
            {ROOT_NAME}
          </div>
          <div className="overflow-y-auto flex-1">
            {renderFileTree(fileStructure)}
          </div>
        </div>

        {/* Editor Section */}
        <div className="flex-1 flex flex-col overflow-y-auto">
          {renderBreadcrumb()}
          <Editor
            theme="vs-dark"
            language={activeLanguage}
            height="100%"
            value={fileContent}
            options={{
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              readOnly: false,
            }}
            beforeMount={(monaco) => {
              monacoRef.current = monaco;
            }}
            onMount={(editor) => {
              editorRef.current = editor;
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default CodeEditor;
