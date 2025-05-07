import { FileText, File, Sheet, Presentation } from "lucide-react";
import React from "react";

export interface FileIconInfo {
  IconComponent: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  bgColor: string;
  label: string;
}

export const getFileIconAndColor = (fileName: string): FileIconInfo => {
  const extension = fileName.split(".").pop()?.toLowerCase() || "";

  // Default values
  let IconComponent = FileText;
  let bgColor = "bg-pink-500";
  let label = extension.toUpperCase();

  // Determine icon and color based on file extension
  switch (extension) {
    case "xlsx":
    case "xls":
    case "csv":
      IconComponent = Sheet;
      bgColor = "bg-[#00A76F]";
      label = "Spreadsheet";
      break;
    case "pdf":
      bgColor = "bg-pink-500";
      label = "PDF";
      break;
    case "doc":
    case "docx":
      bgColor = "bg-blue-500";
      label = "Word";
      break;
    case "ppt":
    case "pptx":
      IconComponent = Presentation;
      bgColor = "bg-orange-500";
      label = "PowerPoint";
      break;
    case "jpg":
    case "jpeg":
    case "png":
    case "gif":
      IconComponent = File;
      bgColor = "bg-purple-500";
      label = "Image";
      break;
    default:
      // Use default values
      break;
  }

  return { IconComponent, bgColor, label };
};
