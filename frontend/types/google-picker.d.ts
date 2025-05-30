// Type definitions for Google Picker API
declare namespace google {
  namespace picker {
    class PickerBuilder {
      addView(view: View): PickerBuilder;
      enableFeature(feature: Feature): PickerBuilder;
      disableFeature(feature: Feature): PickerBuilder;
      setAppId(appId: string): PickerBuilder;
      setAuthUser(user: string): PickerBuilder;
      setCallback(callback: (data: PickerResponse) => void): PickerBuilder;
      setDeveloperKey(key: string): PickerBuilder;
      setDialogTitle(title: string): PickerBuilder;
      setHeight(height: number): PickerBuilder;
      setLocale(locale: string): PickerBuilder;
      setMaxItems(maxItems: number): PickerBuilder;
      setOAuthToken(token: string): PickerBuilder;
      setOrigin(origin: string): PickerBuilder;
      setRelayUrl(url: string): PickerBuilder;
      setSelectableMimeTypes(mimeTypes: string): PickerBuilder;
      setSizeHint(sizeHint: SizeHint): PickerBuilder;
      setUploadToAlbumId(albumId: string): PickerBuilder;
      setVisible(visible: boolean): PickerBuilder;
      setWidth(width: number): PickerBuilder;
      build(): Picker;
    }

    class View {
      setMimeTypes(mimeTypes: string): View;
      setQuery(query: string): View;
      setIncludeFolders(includeFolders: boolean): View;
      setSelectFolderEnabled(selectFolderEnabled: boolean): View;
    }

    class DocsView extends View {}
    class DocsUploadView extends View {}
    class PhotosView extends View {}
    class PhotoAlbumsView extends View {}
    class VideoSearchView extends View {}
    class VideoUploadView extends View {}
    class MapsView extends View {}

    class Picker {
      isVisible(): boolean;
      setVisible(visible: boolean): Picker;
      dispose(): void;
    }

    enum Action {
      CANCEL = "cancel",
      PICKED = "picked",
    }

    enum Feature {
      MULTISELECT_ENABLED = "multiselect",
      NAV_HIDDEN = "navHidden",
      SIMPLE_UPLOAD_ENABLED = "simpleUpload",
    }

    enum ViewId {
      DOCS = "docs",
      DOCS_IMAGES = "docs-images",
      DOCS_VIDEOS = "docs-videos",
      DOCUMENTS = "documents",
      FOLDERS = "folders",
      FORMS = "forms",
      IMAGE_SEARCH = "image-search",
      MAPS = "maps",
      PDFS = "pdfs",
      PHOTO_ALBUMS = "photo-albums",
      PHOTOS = "photos",
      PHOTO_UPLOAD = "photo-upload",
      PRESENTATIONS = "presentations",
      RECENTLY_PICKED = "recently-picked",
      SPREADSHEETS = "spreadsheets",
      VIDEO_SEARCH = "video-search",
      WEBCAM = "webcam",
      YOUTUBE = "youtube",
    }

    interface Document {
      id: string;
      name: string;
      mimeType: string;
      type: string;
      lastEditedUtc: number;
      url: string;
      description: string;
      version: number;
      iconUrl: string;
      serviceId: string;
      parentId: string;
      thumbnailUrl: string;
      embedUrl: string;
      sizeBytes: number;
      rotation: number;
      rotationDegree: number;
      isShared: boolean;
      driveSuccess: boolean;
      uploadState: string;
    }

    interface PickerResponse {
      action: string;
      docs: Document[];
      viewToken: ViewId[];
    }

    enum SizeHint {
      SMALL = 0,
      MEDIUM = 1,
      LARGE = 2,
    }
  }
}

// Extend Window interface to include Google API
interface Window {
  gapi: {
    load(name: string, callback: () => void): void;
  };
  google: typeof google;
}
