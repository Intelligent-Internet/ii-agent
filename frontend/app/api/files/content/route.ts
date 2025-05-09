import { NextResponse } from "next/server";
import fs from "fs/promises";

export async function POST(request: Request) {
  try {
    const { path } = await request.json();
    if (!path) {
      return NextResponse.json({ error: "Path is required" }, { status: 400 });
    }

    const content = await fs.readFile(path, "utf-8");
    return NextResponse.json({ content });
  } catch {
    return NextResponse.json({ error: "Failed to read file" }, { status: 500 });
  }
}
