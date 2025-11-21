import os

# For test-time imports, we want to avoid importing the full server application
# (which triggers a lot of side-effects such as database migrations, storage
# initialization, etc.). Tests can set IIAGENT_SKIP_SERVER_APP_IMPORT=1 to
# prevent importing the server app during test collection.
if os.getenv("IIAGENT_SKIP_SERVER_APP_IMPORT", "0") != "1":
	from .app import create_app

	__all__ = ["create_app"]
else:
	__all__ = []
