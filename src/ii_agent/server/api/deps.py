from typing import Annotated

from fastapi import Depends
from ii_agent.db.manager import get_db, DBSession


async def get_db_session():
    async with get_db() as db:
        yield db


SessionDep = Annotated[DBSession, Depends(get_db_session)]
