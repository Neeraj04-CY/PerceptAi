from fastapi import FastAPI, Request
import traceback
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from routes.auth_routes import router as auth_router
from routes.execute_routes import router as execute_router
from routes.dashboard_routes import router as dashboard_router
from routes.keys_routes import router as keys_router

app = FastAPI(
    title="PerceptAI API",
    description="Universal perception layer for AI agents",
    version="0.1.1"
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__}
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(execute_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(keys_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {
        "name": "PerceptAI API",
        "version": "0.1.1",
        "status": "operational",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"} 

