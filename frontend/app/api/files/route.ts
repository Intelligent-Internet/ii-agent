import { NextResponse } from "next/server";
import fs from "fs/promises";
import path from "path";

interface FileStructure {
  name: string;
  type: "file" | "folder";
  children?: FileStructure[];
  language?: string;
  value?: string;
  path: string;
}

async function readDirectory(dirPath: string): Promise<FileStructure[]> {
  const items = await fs.readdir(dirPath, { withFileTypes: true });
  const result = await Promise.all(
    items.map(async (item) => {
      const fullPath = path.join(dirPath, item.name);
      if (item.isDirectory()) {
        const children = await readDirectory(fullPath);
        return {
          name: item.name,
          type: "folder",
          children,
          path: fullPath,
        };
      } else {
        return {
          name: item.name,
          type: "file",
          path: fullPath,
          language: path.extname(item.name).slice(1) || "plaintext",
        };
      }
    })
  );
  return result as FileStructure[];
}

export async function POST(request: Request) {
  try {
    const { path: dirPath } = await request.json();
    if (!dirPath) {
      return NextResponse.json({ error: "Path is required" }, { status: 400 });
    }

    const files = await readDirectory(dirPath);
    return NextResponse.json({ files });
  } catch (error) {
    console.error("Error reading directory:", error);
    return NextResponse.json(
      { error: "Failed to read directory" },
      { status: 500 }
    );
  }
}
