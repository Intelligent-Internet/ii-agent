import { z } from 'zod';
import { storageService } from '../services/storage.js';
import path from 'path';
import fs from 'fs/promises';

// We define tools that interact with the "Session Workspace"
// In this MVP, we map the session ID to a directory in storage.

export const WriteFileSchema = z.object({
  path: z.string().describe("The relative path to the file to write"),
  content: z.string().describe("The content to write to the file"),
});

export const ReadFileSchema = z.object({
  path: z.string().describe("The relative path to the file to read"),
});

export const ListFilesSchema = z.object({
  path: z.string().optional().describe("The directory to list (defaults to root)"),
});

export const fsDefinitions = [
    {
        name: "write_file",
        description: "Write content to a file in the session workspace",
        schema: WriteFileSchema
    },
    {
        name: "read_file",
        description: "Read content from a file in the session workspace",
        schema: ReadFileSchema
    },
    {
        name: "list_files",
        description: "List files in the session workspace",
        schema: ListFilesSchema
    }
];

export const fsHandlers = {
    write_file: async (input: any, context: { sessionId: string }) => {
        const { path: filePath, content } = input;
        // Security: Ensure we only write to session dir
        // For this MVP, we reuse storageService but we need a specialized method for "workspace" vs "uploads"
        // Let's assume storage/sessions/<sessionId>/workspace is the root

        // Quick implementation:
        // We can use storageService.saveFile but control the path manually?
        // Actually storageService abstracts fileId logic which isn't what we want for a workspace (we want named files).

        const sessionDir = path.join(process.cwd(), 'storage', context.sessionId, 'workspace');
        await fs.mkdir(sessionDir, { recursive: true });

        const targetPath = path.join(sessionDir, filePath);
        if (!targetPath.startsWith(sessionDir)) throw new Error("Access denied");

        await fs.mkdir(path.dirname(targetPath), { recursive: true });
        await fs.writeFile(targetPath, content);

        return { success: true, path: filePath };
    },

    read_file: async (input: any, context: { sessionId: string }) => {
        const { path: filePath } = input;
        const sessionDir = path.join(process.cwd(), 'storage', context.sessionId, 'workspace');
        const targetPath = path.join(sessionDir, filePath);
        if (!targetPath.startsWith(sessionDir)) throw new Error("Access denied");

        const content = await fs.readFile(targetPath, 'utf-8');
        return { content };
    },

    list_files: async (input: any, context: { sessionId: string }) => {
        const dir = input.path || '.';
        const sessionDir = path.join(process.cwd(), 'storage', context.sessionId, 'workspace');
        const targetPath = path.join(sessionDir, dir);
         if (!targetPath.startsWith(sessionDir)) throw new Error("Access denied");

        try {
            const files = await fs.readdir(targetPath);
            return { files };
        } catch {
            return { files: [] };
        }
    }
};
