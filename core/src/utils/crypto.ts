import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

const ALGORITHM = 'aes-256-ctr';
const SECRET_FILE = path.resolve(process.cwd(), '.app_secret');

function getSecretKey(): Buffer {
  if (fs.existsSync(SECRET_FILE)) {
    const hexKey = fs.readFileSync(SECRET_FILE, 'utf-8').trim();
    if (hexKey.length === 64) {
        return Buffer.from(hexKey, 'hex');
    }
  }

  // Generate new key
  const newKey = crypto.randomBytes(32);
  fs.writeFileSync(SECRET_FILE, newKey.toString('hex'), { encoding: 'utf-8' });
  return newKey;
}

const secretKey = getSecretKey();

export function encrypt(text: string): string {
  if (!text) return text;
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv(ALGORITHM, secretKey, iv);
  const encrypted = Buffer.concat([cipher.update(text), cipher.final()]);

  return `${iv.toString('hex')}:${encrypted.toString('hex')}`;
}

export function decrypt(hash: string): string {
  if (!hash) return hash;
  const parts = hash.split(':');
  if (parts.length !== 2) return hash; // Not encrypted or invalid format

  const iv = Buffer.from(parts[0], 'hex');
  const content = Buffer.from(parts[1], 'hex');
  const decipher = crypto.createDecipheriv(ALGORITHM, secretKey, iv);
  const decrypted = Buffer.concat([decipher.update(content), decipher.final()]);

  return decrypted.toString();
}
