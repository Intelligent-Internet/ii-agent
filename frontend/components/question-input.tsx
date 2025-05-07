import { motion } from "framer-motion";
import { ArrowUp, X, Loader2, Paperclip } from "lucide-react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { useState } from "react";
import { getFileIconAndColor } from "@/utils/file-utils";

interface FileUploadStatus {
  name: string;
  loading: boolean;
  error?: string;
}

interface QuestionInputProps {
  className?: string;
  textareaClassName?: string;
  placeholder?: string;
  value: string;
  setValue: (value: string) => void;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (question: string) => void;
  handleFileUpload?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  isUploading?: boolean;
}

const QuestionInput = ({
  className,
  textareaClassName,
  placeholder,
  value,
  setValue,
  handleKeyDown,
  handleSubmit,
  handleFileUpload,
  isUploading = false,
}: QuestionInputProps) => {
  const [files, setFiles] = useState<FileUploadStatus[]>([]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || !handleFileUpload) return;

    // Create file status objects
    const newFiles = Array.from(e.target.files).map((file) => ({
      name: file.name,
      loading: true,
    }));

    setFiles((prev) => [...prev, ...newFiles]);

    // Call the parent handler
    handleFileUpload(e);

    // After a delay, mark files as not loading (this would ideally be handled by the parent)
    setTimeout(() => {
      setFiles((prev) => prev.map((file) => ({ ...file, loading: false })));
    }, 5000);
  };

  const removeFile = (fileName: string) => {
    setFiles((prev) => prev.filter((file) => file.name !== fileName));
  };

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
      <motion.div
        className="relative rounded-xl"
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.1 }}
      >
        {files.length > 0 && (
          <div className="absolute top-2 left-2 right-2 flex flex-wrap gap-2 z-10">
            {files.map((file) => {
              const { IconComponent, bgColor, label } = getFileIconAndColor(
                file.name
              );

              return (
                <div
                  key={file.name}
                  className="flex items-center gap-2 bg-neutral-900 text-black dark:text-white rounded-full px-3 py-2 border border-gray-200 dark:border-gray-700 shadow-sm"
                >
                  <div
                    className={`flex items-center justify-center w-10 h-10 ${bgColor} rounded-full`}
                  >
                    {file.loading ? (
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
                  <button
                    onClick={() => removeFile(file.name)}
                    className="ml-2 rounded-full p-1 hover:bg-gray-200 dark:hover:bg-gray-700"
                  >
                    <X className="size-4" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
        <Textarea
          className={`w-full p-4 rounded-xl !text-lg focus:ring-0 resize-none !placeholder-gray-400 !bg-[#35363a] border-[#ffffff0f] shadow-[0px_0px_10px_0px_rgba(0,0,0,0.02)] ${
            files.length > 0 ? "pt-20 h-60" : "h-40"
          } ${textareaClassName}`}
          placeholder={
            placeholder ||
            "Enter your research query or complex question for in-depth analysis..."
          }
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="flex w-full justify-between items-center absolute bottom-4 px-4">
          {handleFileUpload && (
            <label htmlFor="file-upload" className="cursor-pointer">
              <Button
                variant="ghost"
                size="icon"
                className="hover:bg-gray-700/50 size-10 rounded-full cursor-pointer border border-[#ffffff0f] shadow-sm"
                onClick={() => document.getElementById("file-upload")?.click()}
                disabled={isUploading}
              >
                {isUploading ? (
                  <Loader2 className="size-5 text-gray-400 animate-spin" />
                ) : (
                  <Paperclip className="size-5 text-gray-400" />
                )}
              </Button>
              <input
                id="file-upload"
                type="file"
                multiple
                className="hidden"
                onChange={handleFileChange}
                disabled={isUploading}
              />
            </label>
          )}
          <Button
            disabled={!value.trim()}
            onClick={() => handleSubmit(value)}
            className="cursor-pointer !border !border-red p-4 size-10 font-bold bg-gradient-skyblue-lavender rounded-full hover:scale-105 active:scale-95 transition-transform shadow-[0_4px_10px_rgba(0,0,0,0.1)] dark:shadow-[0_4px_10px_rgba(0,0,0,0.2)]"
          >
            <ArrowUp className="size-5" />
          </Button>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default QuestionInput;
