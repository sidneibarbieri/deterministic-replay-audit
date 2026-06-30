"""FastAPI application for the ActionAudit dashboard."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from arenawealth.api.routers import (
    data_sources_router,
    portfolios_router,
    positions_router,
    providers_router,
    transactions_router,
    user_portfolio_router,
)
from arenawealth.models.database import init_database
from arenawealth.providers.yahoo import YahooProvider

_yahoo_provider: YahooProvider | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize application resources."""
    global _yahoo_provider

    init_database()
    _yahoo_provider = YahooProvider()

    yield

    _yahoo_provider = None


app = FastAPI(
    title="ActionAudit API",
    description="Portfolio analysis API with persistent storage",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_sources_router)
app.include_router(portfolios_router)
app.include_router(positions_router)
app.include_router(providers_router)
app.include_router(transactions_router)
app.include_router(user_portfolio_router)


@app.get("/api/v1/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.2.0",
        "features": ["persistence", "rest-api", "analysis"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
