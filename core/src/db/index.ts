import Database from 'better-sqlite3';
import { v4 as uuidv4 } from 'uuid';
import path from 'path';
import fs from 'fs';

const DB_PATH = process.env.DB_PATH || 'core.sqlite';

export interface Document<T = any> {
  id: string;
  type: string;
  content: T;
  created_at: string;
  updated_at: string;
}

class DB {
  private db: Database.Database;

  constructor() {
    // Ensure directory exists
    const dir = path.dirname(DB_PATH);
    if (dir !== '.' && !fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    this.db = new Database(DB_PATH);
    this.init();
  }

  private init() {
    // Create a single table for storing JSON documents
    // id: UUID
    // type: string (e.g., 'user', 'session', 'llm_setting')
    // content: JSON blob
    // created_at, updated_at: ISO timestamps
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_type ON documents(type);
    `);
  }

  // Generic CRUD
  create<T>(type: string, content: T & { id?: string }): Document<T> {
    const id = content.id || uuidv4();
    const now = new Date().toISOString();

    const stmt = this.db.prepare(`
      INSERT INTO documents (id, type, content, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?)
    `);

    // We store the ID inside the content as well for convenience, but we strip it before saving if it's redundant?
    // Actually, let's keep it simple: content is the full object.
    const docContent = { ...content, id };

    stmt.run(id, type, JSON.stringify(docContent), now, now);

    return {
      id,
      type,
      content: docContent,
      created_at: now,
      updated_at: now
    };
  }

  get<T>(id: string): Document<T> | null {
    const stmt = this.db.prepare('SELECT * FROM documents WHERE id = ?');
    const row = stmt.get(id) as any;

    if (!row) return null;

    return {
      ...row,
      content: JSON.parse(row.content)
    };
  }

  find<T>(type: string, query: (item: T) => boolean): Document<T>[] {
    // Naive implementation: fetch all of type and filter in memory.
    // For a real app, we might want json_extract or virtual tables, but this suffices for now.
    const stmt = this.db.prepare('SELECT * FROM documents WHERE type = ?');
    const rows = stmt.all(type) as any[];

    return rows
      .map(row => ({
        ...row,
        content: JSON.parse(row.content)
      }))
      .filter(doc => query(doc.content));
  }

  findOne<T>(type: string, query: (item: T) => boolean): Document<T> | null {
      const docs = this.find<T>(type, query);
      return docs.length > 0 ? docs[0] : null;
  }

  update<T>(id: string, updates: Partial<T>): Document<T> | null {
    const current = this.get<T>(id);
    if (!current) return null;

    const newContent = { ...current.content, ...updates };
    const now = new Date().toISOString();

    const stmt = this.db.prepare(`
      UPDATE documents
      SET content = ?, updated_at = ?
      WHERE id = ?
    `);

    stmt.run(JSON.stringify(newContent), now, id);

    return {
      ...current,
      content: newContent,
      updated_at: now
    };
  }

  delete(id: string): boolean {
    const stmt = this.db.prepare('DELETE FROM documents WHERE id = ?');
    const info = stmt.run(id);
    return info.changes > 0;
  }
}

export const db = new DB();
