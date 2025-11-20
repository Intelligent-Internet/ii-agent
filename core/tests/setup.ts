import { beforeAll, afterAll, vi } from 'vitest';
import path from 'path';
import fs from 'fs';
import { db } from '../src/db/index.js';

const TEST_DB_PATH = path.join(process.cwd(), 'test_core.sqlite');

beforeAll(() => {
    // Mock DB path to use test DB
    process.env.DB_PATH = TEST_DB_PATH;
    process.env.STORAGE_ROOT = path.join(process.cwd(), 'test_storage');

    // Re-initialize DB with test path
    // Since DB is a singleton instantiated on module load, we might need to hack it or just rely on the env var being set before imports in tests?
    // Actually, 'vitest' loads setup files before test files.
    // But 'src/db/index.ts' might have already been imported if we are not careful.
    // However, in 'vitest', isolation usually helps.
    // A safer bet for integration tests is to delete the test DB before run.

    if (fs.existsSync(TEST_DB_PATH)) {
        fs.unlinkSync(TEST_DB_PATH);
    }
    if (fs.existsSync(process.env.STORAGE_ROOT)) {
        fs.rmSync(process.env.STORAGE_ROOT, { recursive: true, force: true });
    }
});

afterAll(() => {
    // Cleanup
    if (fs.existsSync(TEST_DB_PATH)) {
        fs.unlinkSync(TEST_DB_PATH);
    }
    if (fs.existsSync(process.env.STORAGE_ROOT)) {
        fs.rmSync(process.env.STORAGE_ROOT, { recursive: true, force: true });
    }
});
