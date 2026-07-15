"""FastAPI main application entry point."""

import asyncio
import sys

if sys.platform == "win32":
    # Psycopg's async connection requires a selector-based loop on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import conversation, crew, dsl, workflow
from app.core.langgraph.checkpoint import close_checkpointer, init_checkpointer
from app.core.langgraph.store import close_store, init_store

WEB_DIR = Path(__file__).resolve().parent / "web" / "dist"

# Create FastAPI app with metadata for OpenAPI/Swagger docs
app = FastAPI(
    title="Agent Workflow Kit API",
    description="API for composable LangGraph agent workflows.",
    version="0.1.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(conversation.chat_router, prefix="/api")
app.include_router(conversation.router, prefix="/api")
app.include_router(crew.router, prefix="/api")
app.include_router(workflow.router, prefix="/api")
app.include_router(dsl.router, prefix="/api")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# Add other routers here as they are implemented
# app.include_router(mcp_servers_router, prefix="/api")

# Health check endpoint
@app.get("/api/health", tags=["health"])
async def health_check():
    """Health check endpoint to verify the API is running"""
    return {"status": "ok", "version": app.version}


@app.get("/", include_in_schema=False)
async def web_app():
    """Serve the React workflow studio."""

    return FileResponse(WEB_DIR / "index.html")


@app.on_event("startup")
async def startup_event():
    """Run tasks on application startup"""
    # Initialize database connections, caches, etc.
    await init_checkpointer()
    await init_store()


@app.on_event("shutdown")
async def shutdown_event():
    """Run tasks on application shutdown"""
    # Clean up resources
    await close_store()
    await close_checkpointer()


if __name__ == "__main__":
    import uvicorn

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        reload=False,
    )
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())
