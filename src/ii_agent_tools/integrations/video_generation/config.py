from pydantic import BaseModel


class VideoGenerateConfig(BaseModel):
    gcp_project_id: str | None = None
    gcp_location: str | None = None
    gcs_output_bucket: str | None = None
    google_ai_studio_api_key: str | None = None
    custom_domain: str | None = None
    fal_api_key: str | None = None
    fal_model_name: str | None = None
    fal_request_mode: str = "async"
    minimax_api_key: str | None = None
    minimax_base_url: str = "https://api.minimax.io/v1"
    minimax_model_name: str | None = "MiniMax-H3"
    minimax_group_id: str | None = None
