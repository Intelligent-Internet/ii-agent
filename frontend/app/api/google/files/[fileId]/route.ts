import { NextRequest, NextResponse } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ fileId: string }> }
) {
  const accessToken = request.cookies.get("google_access_token")?.value;
  const { fileId } = await params;

  if (!accessToken) {
    return NextResponse.json(
      { error: "Not authenticated with Google Drive" },
      { status: 401 }
    );
  }

  try {
    // First, get file metadata to determine the mime type
    const metadataResponse = await fetch(
      `https://www.googleapis.com/drive/v3/files/${fileId}?fields=name,mimeType&supportsAllDrives=true`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }
    );

    if (!metadataResponse.ok) {
      const errorData = await metadataResponse.json();
      console.error("Google Drive API error:", errorData.error.errors);

      if (metadataResponse.status === 401) {
        const res = NextResponse.json(
          { error: "Google Drive authentication expired" },
          { status: 401 }
        );
        res.cookies.delete("google_access_token");
        return res;
      }

      return NextResponse.json(
        { error: "Failed to fetch file metadata from Google Drive" },
        { status: metadataResponse.status }
      );
    }

    const metadata = await metadataResponse.json();

    // Now download the file content
    const contentResponse = await fetch(
      `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }
    );

    if (!contentResponse.ok) {
      const errorText = await contentResponse.text();
      console.error("Google Drive API error:", errorText);

      return NextResponse.json(
        { error: "Failed to download file from Google Drive" },
        { status: contentResponse.status }
      );
    }

    // For binary files, return as blob
    if (
      metadata.mimeType.startsWith("image/") ||
      metadata.mimeType === "application/pdf"
    ) {
      const blob = await contentResponse.blob();
      const buffer = await blob.arrayBuffer();
      const base64 = Buffer.from(buffer).toString("base64");

      return NextResponse.json({
        name: metadata.name,
        mimeType: metadata.mimeType,
        content: `data:${metadata.mimeType};base64,${base64}`,
      });
    }

    // For text files, return as text
    const text = await contentResponse.text();
    return NextResponse.json({
      name: metadata.name,
      mimeType: metadata.mimeType,
      content: text,
    });
  } catch (error) {
    console.error("Error downloading file from Google Drive:", error);
    return NextResponse.json(
      { error: "Failed to download file from Google Drive" },
      { status: 500 }
    );
  }
}
