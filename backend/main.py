from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS is intentionally open for local development and GitHub Codespaces.
# Restrict to specific origins before deploying to a public server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """Health-check endpoint – confirms the backend is up."""
    return {"status": "LinguaBridge running"}
