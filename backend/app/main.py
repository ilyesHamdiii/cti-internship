from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.routes import router as api_router
from app.db.session import SessionLocal
from app.services.bootstrap import seed_baseline


def create_app() -> FastAPI:
    app = FastAPI(title="CTI Detection Engineering Platform", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup() -> None:
        db = SessionLocal()
        try:
            seed_baseline(db)
        finally:
            db.close()

    @app.exception_handler(Exception)
    async def exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": str(exc), "details": {}}},
        )

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
