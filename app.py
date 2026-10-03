"""ScamGuard API entrypoint. Start with ``python -m uvicorn app:app --reload``."""
from src.api import app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
