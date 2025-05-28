import { NextRequest, NextResponse } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ folderId: string }> }
) {
  const accessToken = request.cookies.get("google_access_token")?.value;
  const { folderId } = await params;

  if (!accessToken) {
    return NextResponse.json(
      { error: "Not authenticated with Google Drive" },
      { status: 401 }
    );
  }

  try {
    // Fetch files in the folder using Google Drive API
    const response = await fetch(
      `https://www.googleapis.com/drive/v3/files?q='${folderId}'+in+parents+and+trashed=false&fields=files(id,name,mimeType)&supportsAllDrives=true&includeItemsFromAllDrives=true`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json();
      console.error("Google Drive API error:", errorData.error);

      if (response.status === 401) {
        const res = NextResponse.json(
          { error: "Google Drive authentication expired" },
          { status: 401 }
        );
        res.cookies.delete("google_access_token");
        return res;
      }

      return NextResponse.json(
        { error: "Failed to fetch folder contents from Google Drive" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching folder contents from Google Drive:", error);
    return NextResponse.json(
      { error: "Failed to fetch folder contents from Google Drive" },
      { status: 500 }
    );
  }
}
