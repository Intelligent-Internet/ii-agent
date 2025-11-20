import fs from 'fs/promises';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

const STORAGE_ROOT = process.env.STORAGE_ROOT || path.join(process.cwd(), 'storage');

export class StorageService {
  constructor() {
    this.init();
  }

  private async init() {
    try {
      await fs.mkdir(STORAGE_ROOT, { recursive: true });
    } catch (error) {
      console.error('Failed to initialize storage:', error);
    }
  }

  async saveFile(filename: string, content: Buffer | string, sessionId?: string): Promise<string> {
    const fileId = uuidv4();
    // Organize by session if provided, else generic uploads
    const subDir = sessionId ? path.join(STORAGE_ROOT, sessionId) : path.join(STORAGE_ROOT, 'uploads');

    await fs.mkdir(subDir, { recursive: true });

    const ext = path.extname(filename);
    const storedFilename = `${fileId}${ext}`;
    const fullPath = path.join(subDir, storedFilename);

    await fs.writeFile(fullPath, content);

    // Return relative path for retrieval
    const relativePath = path.relative(STORAGE_ROOT, fullPath);
    return relativePath;
  }

  async getFile(relativePath: string): Promise<Buffer> {
    const fullPath = path.join(STORAGE_ROOT, relativePath);
    // Basic path traversal protection
    if (!fullPath.startsWith(STORAGE_ROOT)) {
      throw new Error('Invalid file path');
    }
    return fs.readFile(fullPath);
  }

  async listFiles(sessionId: string): Promise<string[]> {
      const sessionDir = path.join(STORAGE_ROOT, sessionId);
      try {
          return await fs.readdir(sessionDir);
      } catch {
          return [];
      }
  }

  getStoragePath(relativePath: string): string {
      return path.join(STORAGE_ROOT, relativePath);
  }
}

export const storageService = new StorageService();
