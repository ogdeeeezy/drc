"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="Agentic DRC",
    description="Open-source DRC tool for semiconductor layout verification",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}
