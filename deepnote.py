from app.main import app
import uvicorn

if __name__ == "__main__":
    # Deepnote uses port 8000 by default
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Required for Deepnote
        port=8000,
        workers=2,  # 2 CPU optimization
        limit_concurrency=50,
        timeout_keep_alive=30,
        loop="uvloop",
        log_level="info"
    )
