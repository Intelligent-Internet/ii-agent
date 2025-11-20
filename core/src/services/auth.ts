import { db, Document } from '../db/index.js';
import { User, UserSchema } from '../db/schema.js';
import { v4 as uuidv4 } from 'uuid';

export class AuthService {
  async createAnonymousUser(): Promise<Document<User>> {
    const newUser: User = {
      id: uuidv4(),
      is_anonymous: true,
      role: 'user',
      email: `anonymous_${Date.now()}@example.com`, // Placeholder
    };

    return db.create('user', newUser);
  }

  async getUser(id: string): Promise<Document<User> | null> {
    return db.get<User>(id);
  }
}

export const authService = new AuthService();
