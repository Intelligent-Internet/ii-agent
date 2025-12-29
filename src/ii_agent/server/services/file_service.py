import uuid
import requests
from typing import List
from dataclasses import dataclass
from ii_agent.db.manager import Files
from ii_agent.storage import BaseStorage
from ii_agent.core.storage.locations import get_session_file_path


@dataclass
class FileData:
    id: str
    name: str
    size: int
    content_type: str
    storage_path: str | None = None
    url: str | None = None
    

class FileService:
    
    def __init__(self, storage: BaseStorage):
        self.storage = storage

    def _generate_file_id(self) -> str:
        return str(uuid.uuid4())

    async def get_file_by_id(self, file_id: str) -> FileData:
        file = await Files.get_file_by_id(file_id)
        if not file:
            raise FileNotFoundError(f"File with id {file_id} not found")
        
        signed_url = None
        if file.storage_path:
            # Use internal=True for URLs that will be used by sandbox-server (container-to-container)
            signed_url = self.storage.get_download_signed_url(file.storage_path, internal=True)
    
        return FileData(
            id=file.id,
            name=file.file_name,
            size=file.file_size,
            content_type=file.content_type,
            storage_path=file.storage_path,
            url=signed_url,
        )

    async def get_files_by_session_id(self, session_id: str) -> List[FileData]:
        files = await Files.get_files_by_session_id(session_id)
        if files is None:
            raise FileNotFoundError(f"No files found for session {session_id}")
        
        return [
            FileData(
                id=file.id,
                name=file.file_name,
                size=file.file_size,
                content_type=file.content_type,
                storage_path=file.storage_path,
                url=self.storage.get_download_signed_url(file.storage_path) if file.storage_path else None,
            )
            for file in files
        ]

    async def update_file_session_id(self, file_id: str, session_id: str):
        await Files.update_session_id(file_id, session_id)

    async def write_file_from_url(
        self, 
        url: str,
        file_name: str,
        file_size: int,
        content_type: str,
        session_id: str,
        ) -> FileData:
        file_id = self._generate_file_id()
        storage_path = get_session_file_path(session_id, file_id, file_name)
        await Files.create_file(
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            storage_path=storage_path,
            content_type=content_type,
            session_id=session_id,
        )

        self.storage.write_from_url(url, storage_path, content_type)

        return FileData(
            id=file_id,
            name=file_name,
            size=file_size,
            content_type=content_type,
            storage_path=storage_path,
        )