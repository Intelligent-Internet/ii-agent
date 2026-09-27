"""Composio Toolkit Service - handles toolkit discovery and metadata."""

from typing import TYPE_CHECKING, List, Dict, Any, Optional
from pydantic import BaseModel

from .client import ComposioClient
from .cache_service import ComposioCacheService

from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from composio import Composio


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Convert various object types to dictionary.

    Handles Pydantic models, objects with __dict__, and dicts.
    """
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return {}


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Get attribute from object or dict safely."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def tool_requires_sandbox(toolkit_slug: str) -> bool:
    """Return True if toolkit operations should run inside a sandbox."""
    return ToolkitService.requires_sandbox(toolkit_slug)


class CategoryInfo(BaseModel):
    """Toolkit category information."""

    id: str
    name: str


class ToolkitInfo(BaseModel):
    """Basic toolkit information."""

    slug: str
    name: str
    description: Optional[str] = None
    logo: Optional[str] = None
    auth_schemes: List[str] = []
    categories_info: List[CategoryInfo] = []
    tools_count: Optional[int] = None
    app_url: Optional[str] = None


class AuthConfigField(BaseModel):
    """Authentication configuration field."""

    name: str
    displayName: str
    type: str
    description: Optional[str] = None
    required: bool = False
    default: Optional[str] = None
    legacy_template_name: Optional[str] = None


class AuthConfigDetails(BaseModel):
    """Authentication configuration details."""

    name: str
    mode: str
    fields: Dict[str, Dict[str, List[AuthConfigField]]]


class DetailedToolkitInfo(BaseModel):
    """Detailed toolkit information including auth requirements."""

    slug: str
    name: str
    description: Optional[str] = None
    logo: Optional[str] = None
    auth_schemes: List[str] = []
    categories_info: List[CategoryInfo] = []
    auth_config_details: List[AuthConfigDetails] = []
    connected_account_initiation_fields: Optional[Dict[str, List[AuthConfigField]]] = None
    base_url: Optional[str] = None


class ToolkitService:
    """Service for Composio toolkit operations."""

    def __init__(
        self, *, cache_service: ComposioCacheService | None = None, api_key: str | None = None
    ) -> None:
        self._cache_service = cache_service
        self._api_key = api_key
        self._client: "Composio | None" = None

    @property
    def client(self) -> "Composio | None":
        """Lazy-init the Composio client on first use.  Returns *None* when unconfigured."""
        if self._client is None:
            try:
                self._client = ComposioClient.get_client(self._api_key)
            except ValueError:
                return None
        return self._client

    # Toolkits that must run inside a sandbox (e.g., file/storage access)
    SANDBOX_REQUIRED_TOOLKITS = {
        "googledrive",
    }

    # Actions to exclude from specific toolkits
    EXCEPT_TOOLKIT = {
        "googledrive": ["GOOGLEDRIVE_UPLOAD_FILE"],
        "gmail": ["GMAIL_SEND_EMAIL"],
    }

    # Popular categories for filtering toolkits
    CATEGORIES = [
        CategoryInfo(id="popular", name="Popular"),
        CategoryInfo(id="productivity", name="Productivity"),
        CategoryInfo(id="crm", name="CRM"),
        CategoryInfo(id="marketing", name="Marketing"),
        CategoryInfo(id="analytics", name="Analytics"),
        CategoryInfo(id="communication", name="Communication"),
        CategoryInfo(id="project-management", name="Project Management"),
        CategoryInfo(id="scheduling", name="Scheduling"),
    ]

    # Manual mapping for common apps to professional display names
    DISPLAY_NAME_MAP = {
        # Google Apps
        "gmail": "Gmail",
        "googlecalendar": "Google Calendar",
        "googledrive": "Google Drive",
        "googlesheets": "Google Sheets",
        "googledocs": "Google Docs",
        "googleslides": "Google Slides",
        "googlemeet": "Google Meet",
        "googletasks": "Google Tasks",
        "youtube": "YouTube",
        "googlephotos": "Google Photos",
        "google_maps": "Google Maps",
        # Microsoft Apps
        "outlook": "Outlook",
        "one_drive": "OneDrive",
        "microsoft_teams": "Microsoft Teams",
        # Productivity
        "slack": "Slack",
        # "slackbot": "Slackbot",
        "notion": "Notion",
        # "asana": "Asana",
        # "trello": "Trello",
        # "monday": "Monday.com",
        # "clickup": "ClickUp",
        # "airtable": "Airtable",
        # "evernote": "Evernote",
        "todoist": "Todoist",
        # # CRM & Sales
        # "salesforce": "Salesforce",
        # "hubspot": "HubSpot",
        # "zendesk": "Zendesk",
        # "freshdesk": "Freshdesk",
        # "intercom": "Intercom",
        # "pipedrive": "Pipedrive",
        # "zohocrm": "Zoho CRM",
        # Communication
        "discord": "Discord",
        # "discordbot": "Discordbot",
        # "telegram": "Telegram",
        # "whatsapp": "WhatsApp",
        # "twilio": "Twilio",
        # Development
        "github": "GitHub",
        "gitlab": "GitLab",
        # "bitbucket": "Bitbucket",
        # "jira": "Jira",
        # "linear": "Linear",
        # "browserbase": "Browserbase",
        # "browserbase_tool": "Browserbase",
        # "vercel": "Vercel",
        # "netlify": "Netlify",
        # # Marketing
        # "mailchimp": "Mailchimp",
        # "sendgrid": "SendGrid",
        # "typeform": "Typeform",
        # Storage
        "dropbox": "Dropbox",
        # "box": "Box",
        # # AI & Automation
        # "openai": "OpenAI",
        # "anthropic": "Anthropic",
        # "perplexityai": "Perplexity AI",
        # "zapier": "Zapier",
        # Other
        # "shopify": "Shopify",
        # "stripe": "Stripe",
        # "paypal": "PayPal",
        # "calendly": "Calendly",
        "zoom": "Zoom",
        # "loom": "Loom",
        "figma": "Figma",
        "canva": "Canva",
        "miro": "Miro",
        # "spotify": "Spotify",
        "twitter": "Twitter",
        # "linkedin": "LinkedIn",
        # "facebook": "Facebook",
        # "instagram": "Instagram",
        # "tiktok": "TikTok",
        "reddit": "Reddit",
        "supabase": "Supabase",
        # "firebase": "Firebase",
        # "aws": "AWS",
        # "gcp": "Google Cloud",
        # "azure": "Azure",
    }

    def _slugify_to_display_name(self, slug: str) -> str:
        """Convert a slug to a professional display name.

        Args:
            slug: The app slug (e.g., "googlecalendar", "browserbase_tool")

        Returns:
            Professional display name (e.g., "Google Calendar", "Browserbase")
        """
        # Check manual mapping first
        if slug.lower() in self.DISPLAY_NAME_MAP:
            return self.DISPLAY_NAME_MAP[slug.lower()]

        # Remove common suffixes
        slug = slug.replace("_tool", "").replace("_api", "").replace("_app", "")

        # Split on underscores and capitalize
        if "_" in slug:
            words = slug.split("_")
            return " ".join(word.capitalize() for word in words)

        # Handle camelCase or compound words
        # Insert space before capitals (googlecalendar -> google calendar)
        import re

        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", slug)

        # Split by spaces and capitalize each word
        words = spaced.split()

        # Special handling for common prefixes
        result_words = []
        for i, word in enumerate(words):
            word_lower = word.lower()
            # Capitalize known brand prefixes
            if word_lower in ["google", "microsoft", "facebook", "amazon", "apple"]:
                result_words.append(word.capitalize())
            # Keep acronyms uppercase if already uppercase
            elif word.isupper() and len(word) <= 4:
                result_words.append(word)
            else:
                result_words.append(word.capitalize())

        return " ".join(result_words) if result_words else slug.capitalize()

    @classmethod
    def requires_sandbox(cls, toolkit_slug: str) -> bool:
        """Return True if toolkit operations should run inside a sandbox."""
        return toolkit_slug.lower() in cls.SANDBOX_REQUIRED_TOOLKITS

    def _extract_toolkit_info(self, item: Any) -> Optional[ToolkitInfo]:
        """Extract ToolkitInfo from a Composio app object.

        Returns None if the app should be skipped (e.g., no_auth apps or not in DISPLAY_NAME_MAP).
        """
        data = _to_dict(item)

        # Skip apps that don't require auth
        if data.get("no_auth", False):
            return None

        meta = _to_dict(data.get("meta", {}))

        # Extract auth schemes, default to OAUTH2 for apps requiring auth
        auth_schemes = data.get("auth_schemes") or ["OAUTH2"]

        # Extract categories with id and name
        categories_data = _get_attr(meta, "categories", [])
        categories_info = []

        for cat in categories_data:
            if isinstance(cat, dict) or hasattr(cat, "__dict__"):
                cat_dict = _to_dict(cat)
                cat_id = cat_dict.get("id", "")
                cat_name = cat_dict.get("name", "").title()
                if cat_id and cat_name:
                    categories_info.append(CategoryInfo(id=cat_id, name=cat_name))

        slug = data.get("key") or data.get("slug", "")
        raw_name = data.get("name", "")

        # Skip apps not in DISPLAY_NAME_MAP
        if slug.lower() not in self.DISPLAY_NAME_MAP:
            return None

        # Convert slug to professional display name
        display_name = self._slugify_to_display_name(raw_name or slug)

        # Extract tools_count and app_url from meta
        tools_count = _get_attr(meta, "tools_count")
        if tools_count is not None and isinstance(tools_count, float):
            tools_count = int(tools_count)

        app_url = _get_attr(meta, "app_url")

        return ToolkitInfo(
            slug=slug,
            name=display_name,
            description=_get_attr(meta, "description") or data.get("description"),
            logo=_get_attr(meta, "logo") or data.get("logo"),
            auth_schemes=auth_schemes,
            categories_info=categories_info,
            tools_count=tools_count,
            app_url=app_url,
        )

    _EMPTY_TOOLKITS_RESPONSE: Dict[str, Any] = {
        "success": True,
        "toolkits": [],
        "categories": [],
        "total_items": 0,
        "total_pages": 1,
        "current_page": 1,
        "next_cursor": None,
        "has_more": False,
    }

    async def list_toolkits(
        self, limit: int = 500, cursor: Optional[str] = None, category: Optional[str] = None
    ) -> Dict[str, Any]:
        """List available toolkits with OAuth2 support.

        Args:
            limit: Maximum number of toolkits to return
            cursor: Pagination cursor (not used currently)
            category: Filter by category (not used currently)

        Returns:
            Dict containing toolkits, categories, and pagination info
        """
        if self.client is None:
            return self._EMPTY_TOOLKITS_RESPONSE

        logger.debug(f"Fetching toolkits with limit: {limit}, category: {category}")

        # Try to get from cache first (only if no filters applied)
        cached_result = (
            await self._cache_service.get_all_toolkits() if self._cache_service else None
        )
        if cached_result:
            logger.debug("Using cached toolkits list")
            return cached_result

        apps_list = self.client.toolkits.get()
        items = apps_list if isinstance(apps_list, list) else []

        # Convert apps to ToolkitInfo, filtering out no_auth apps
        toolkits = [
            info for item in items if (info := self._extract_toolkit_info(item)) is not None
        ]

        # Extract unique categories from all toolkits
        categories_set = {}
        for toolkit in toolkits:
            for cat_info in toolkit.categories_info:
                if cat_info.id not in categories_set:
                    categories_set[cat_info.id] = cat_info

        # Always include "all" and "popular" as special categories
        all_categories = [
            CategoryInfo(id="all", name="All Apps"),
            CategoryInfo(id="popular", name="Popular"),
        ]

        # Add extracted categories sorted by name
        extracted_categories = sorted(categories_set.values(), key=lambda c: c.name)
        all_categories.extend(extracted_categories)

        # Apply limit
        if limit and limit < len(toolkits):
            toolkits = toolkits[:limit]

        logger.debug(
            f"Successfully fetched {len(toolkits)} toolkits with {len(all_categories)} categories"
        )

        result = {
            "success": True,
            "toolkits": toolkits,
            "categories": all_categories,
            "total_items": len(toolkits),
            "total_pages": 1,
            "current_page": 1,
            "next_cursor": None,
            "has_more": False,
        }

        # Convert ToolkitInfo and CategoryInfo objects to dicts for caching
        cache_result = result.copy()
        cache_result["toolkits"] = [t.model_dump() for t in toolkits]
        cache_result["categories"] = [c.model_dump() for c in all_categories]
        if self._cache_service:
            await self._cache_service.set_all_toolkits(cache_result)

        return result

    async def get_toolkit_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Get a specific toolkit by slug.

        Args:
            slug: Toolkit slug (e.g., "gmail")

        Returns:
            Dict of ToolkitInfo or None if not found
        """
        toolkits_response = await self.list_toolkits()
        toolkits = toolkits_response.get("toolkits", [])

        for toolkit in toolkits:
            if toolkit.get("slug") == slug:
                return toolkit
        return None

    def _matches_search(self, toolkit: Dict[str, Any], query: str) -> bool:
        """Check if toolkit matches search query."""
        query_lower = query.lower()
        return (
            query_lower in toolkit.get("name", "").lower()
            or (
                toolkit.get("description", "")
                and query_lower in toolkit.get("description", "").lower()
            )
            or any(
                query_lower in cat.get("name", "").lower()
                for cat in toolkit.get("categories_info", [])
            )
        )

    async def search_toolkits(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search toolkits by query string.

        Args:
            query: Search query
            category: Filter by category
            limit: Maximum number of results
            cursor: Pagination cursor (not used currently)

        Returns:
            Dict containing search results and pagination info
        """
        all_response = await self.list_toolkits(limit=500, category=category)
        toolkits = all_response.get("toolkits", [])

        filtered = [t for t in toolkits if self._matches_search(t, query)]
        limited = filtered[:limit]

        logger.debug(f"Found {len(filtered)} toolkits matching query: {query}")

        return {
            "success": True,
            "toolkits": limited,
            "total_items": len(filtered),
            "total_pages": 1,
            "current_page": 1,
            "next_cursor": None,
            "has_more": False,
        }

    async def get_toolkit_icon(self, toolkit_slug: str) -> Optional[str]:
        """Get toolkit logo/icon URL.

        Args:
            toolkit_slug: Toolkit slug

        Returns:
            Logo URL or None
        """
        # Try cache first
        cached_icon = (
            await self._cache_service.get_toolkit_icon(toolkit_slug)
            if self._cache_service
            else None
        )
        if cached_icon is not None:
            logger.debug(f"Using cached icon for {toolkit_slug}")
            return cached_icon

        if self.client is None:
            return None

        try:
            response = self.client.toolkits.get(toolkit_slug)
            data = _to_dict(response)
            meta = _to_dict(data.get("meta", {}))
            icon_url = _get_attr(meta, "logo")

            # Cache the icon URL
            if self._cache_service:
                await self._cache_service.set_toolkit_icon(toolkit_slug, icon_url)

            return icon_url
        except Exception as e:
            logger.error(f"Failed to get toolkit icon for {toolkit_slug}: {e}")
            return None

    def _parse_auth_config_field(self, field: Any) -> AuthConfigField:
        """Parse a single auth config field."""
        field_dict = _to_dict(field)
        return AuthConfigField(
            name=field_dict.get("name", ""),
            displayName=field_dict.get("display_name", ""),
            type=field_dict.get("type", "string"),
            description=field_dict.get("description"),
            required=field_dict.get("required", False),
            default=field_dict.get("default"),
            legacy_template_name=field_dict.get("legacy_template_name"),
        )

    def _parse_auth_config_details(
        self, raw_configs: List[Any]
    ) -> tuple[List[AuthConfigDetails], Optional[Dict[str, List[AuthConfigField]]]]:
        """Parse auth config details and connected account initiation fields.

        Returns:
            Tuple of (auth_config_details, connected_account_initiation_fields)
        """
        auth_config_details = []
        connected_account_initiation = None

        for config in raw_configs:
            config_dict = _to_dict(config)
            fields_dict = _to_dict(config_dict.get("fields", {}))

            auth_fields: Dict[str, Dict[str, List[AuthConfigField]]] = {}

            for field_type, field_type_obj in fields_dict.items():
                if field_type == "connected_account_initiation":
                    # Handle initiation fields separately
                    if connected_account_initiation is None:
                        initiation_dict = _to_dict(field_type_obj)
                        connected_account_initiation = {
                            level: [
                                self._parse_auth_config_field(f)
                                for f in initiation_dict.get(level, [])
                            ]
                            for level in ["required", "optional"]
                        }
                    continue

                field_type_dict = _to_dict(field_type_obj)
                auth_fields[field_type] = {
                    level: [
                        self._parse_auth_config_field(f) for f in field_type_dict.get(level, [])
                    ]
                    for level in ["required", "optional"]
                }

            auth_config_details.append(
                AuthConfigDetails(
                    name=config_dict.get("name", ""),
                    mode=config_dict.get("mode", ""),
                    fields=auth_fields,
                )
            )

        return auth_config_details, connected_account_initiation

    async def get_detailed_toolkit_info(self, toolkit_slug: str) -> Optional[DetailedToolkitInfo]:
        """Get detailed toolkit information including auth requirements.

        Args:
            toolkit_slug: Toolkit slug

        Returns:
            DetailedToolkitInfo with auth configuration details
        """
        logger.debug(f"Fetching detailed toolkit info for: {toolkit_slug}")

        # Try cache first
        cached_details = (
            await self._cache_service.get_toolkit_details(toolkit_slug)
            if self._cache_service
            else None
        )
        if cached_details:
            logger.debug(f"Using cached details for {toolkit_slug}")
            return DetailedToolkitInfo(**cached_details)

        if self.client is None:
            return None

        response = self.client.tools.get_raw_composio_tools(toolkits=[toolkit_slug], limit=1)
        data = _to_dict(response[0]) if response else None
        meta = _to_dict(data.get("meta", {}))

        # Extract categories with id and name
        categories_data = _get_attr(meta, "categories", [])
        categories_info = []

        for cat in categories_data:
            if isinstance(cat, dict) or hasattr(cat, "__dict__"):
                cat_dict = _to_dict(cat)
                cat_id = cat_dict.get("id", "")
                cat_name = cat_dict.get("name", "")
                if cat_id and cat_name:
                    categories_info.append(CategoryInfo(id=cat_id, name=cat_name))

        # Parse auth configurations
        raw_auth_configs = data.get("auth_config_details", [])
        auth_config_details, initiation_fields = self._parse_auth_config_details(raw_auth_configs)

        # Convert slug to professional display name
        slug = data.get("slug", "")
        raw_name = data.get("name", "")
        display_name = self._slugify_to_display_name(raw_name or slug)

        detailed_toolkit = DetailedToolkitInfo(
            slug=slug,
            name=display_name,
            description=_get_attr(meta, "description", ""),
            logo=_get_attr(meta, "logo"),
            auth_schemes=data.get("composio_managed_auth_schemes", []),
            categories_info=categories_info,
            base_url=data.get("base_url"),
            auth_config_details=auth_config_details,
            connected_account_initiation_fields=initiation_fields,
        )

        # Cache the result
        if self._cache_service:
            await self._cache_service.set_toolkit_details(
                toolkit_slug, detailed_toolkit.model_dump()
            )

        logger.debug(f"Successfully fetched detailed info for {toolkit_slug}")
        return detailed_toolkit
