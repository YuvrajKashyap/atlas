from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from atlas.services.runs import RunStateError
from atlas.urls import UrlPolicyError


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LookupError)
    async def not_found_handler(_request: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RunStateError)
    async def run_state_handler(_request: Request, exc: RunStateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(UrlPolicyError)
    async def url_policy_handler(_request: Request, exc: UrlPolicyError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
