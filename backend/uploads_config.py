import os
from pathlib import Path


UPLOAD_DIR = Path("/tmp/uploads") if os.environ.get("VERCEL") else Path("uploads")
UPLOAD_URL_PREFIX = "/uploads"
