from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.core.config import CORS_ALLOW_ORIGINS


class CorsFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        # Wrap error handling too, so 500 responses are visible to browser clients.
        return CORSMiddleware(
            super().build_middleware_stack(),
            allow_origins=CORS_ALLOW_ORIGINS,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["Retry-After"],
        )
