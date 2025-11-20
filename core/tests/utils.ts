import { db } from '../src/db/index.js';
import { v4 as uuidv4 } from 'uuid';

export function createTestUser() {
    return db.create('user', {
        id: uuidv4(),
        is_anonymous: true,
        role: 'user',
        email: 'test@example.com'
    }).content;
}

export function createTestSession(userId: string) {
    return db.create('session', {
        id: uuidv4(),
        user_id: userId,
        status: 'active',
        prompt_tokens: 0,
        completion_tokens: 0,
        cost: 0
    }).content;
}
