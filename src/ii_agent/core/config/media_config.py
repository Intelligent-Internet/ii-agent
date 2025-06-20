from pydantic import BaseModel, Field


class MediaConfig(BaseModel):
    """Configuration for media generation tools.
    
    Attributes:
        gcp_project_id: The Google Cloud Project ID for Vertex AI.
        gcp_location: The Google Cloud location/region for Vertex AI.
        gcs_output_bucket: The GCS bucket URI for storing temporary media files.
    """
    gcp_project_id: str | None = Field(default=None, description="Google Cloud Project ID for Vertex AI")
    gcp_location: str | None = Field(default=None, description="Google Cloud location/region for Vertex AI") 
    gcs_output_bucket: str | None = Field(default=None, description="GCS bucket URI for storing temporary media files (e.g., gs://my-bucket-name)") 