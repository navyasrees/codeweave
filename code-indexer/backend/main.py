import sys
import os
import re
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path



# Ensure imports (bootstrap/indexer/etc.) resolve from the local project root.
# This avoids accidentally picking up a different `bootstrap.py` elsewhere in sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.query_engine import load_resources, query
from backend.indexer_job import create_job, get_job
from backend.pipeline_runner import run_pipeline


ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

resources_cache = {}

def get_resources(repo_name: str):
    if repo_name not in resources_cache:
        resources_cache[repo_name] = load_resources(repo_name)
    return resources_cache[repo_name]

class QueryRequest(BaseModel):
    question: str
    repo_name: str = "fastapi"  # default to fastapi

@app.post("/query")
def handle_query(request: QueryRequest):
    repo_name = request.repo_name  # add this field to QueryRequest
    G, collection, model = get_resources(repo_name)
    result = query(request.question, G, collection, model)
    return {
        "answer": result["answer"],
        "mode": result["mode"],
        "node_count": result["node_count"],
    }

class IndexRequest(BaseModel):
    github_url: str

@app.post("/index")
def start_index(request: IndexRequest):
    job_id = create_job()

    def run_and_clear(job_id, github_url):
        run_pipeline(job_id, github_url=github_url)
        # clear cache so next query reloads fresh collection
        repo_name = get_job(job_id).get("repo_name")
        if repo_name and repo_name in resources_cache:
            del resources_cache[repo_name]

    thread = threading.Thread(
        target=run_and_clear,
        args=(job_id, request.github_url),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


def _safe_repo_name(name: str) -> str:
    """Sanitise an arbitrary string into a filesystem-safe repo name slug."""
    name = re.sub(r"\.zip$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-._")
    return name or "uploaded-repo"


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a zip while refusing path-traversal attempts (../, absolute paths)."""
    dest_resolved = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if not str(target).startswith(str(dest_resolved)):
            raise ValueError(f"Refusing unsafe path in archive: {member.filename}")
    zf.extractall(dest)


@app.post("/index/upload")
async def upload_index(
    file: UploadFile = File(...),
    repo_name: str = Form(None),
):
    """Accept a .zip of a local folder, extract it, and run the indexing pipeline."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        return {"error": "Only .zip files are supported"}

    name = _safe_repo_name(repo_name or file.filename)
    artifact_dir = ARTIFACTS_DIR / name
    repo_path = artifact_dir / "repo"

    # Wipe any prior extraction for this name
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True, exist_ok=True)

    # Spool the upload to a temp file, then extract
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1 << 20)  # 1 MB
                if not chunk:
                    break
                tmp.write(chunk)

        with zipfile.ZipFile(tmp_path, "r") as zf:
            _safe_extract(zf, repo_path)
    except zipfile.BadZipFile:
        return {"error": "File is not a valid .zip archive"}
    except ValueError as e:
        return {"error": str(e)}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # If the zip wraps everything in a single top-level dir (common with `git archive`
    # or GitHub-style "Source code (zip)"), flatten it so the pipeline sees the repo
    # contents directly under repo_path.
    entries = list(repo_path.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for item in inner.iterdir():
            shutil.move(str(item), str(repo_path / item.name))
        inner.rmdir()

    job_id = create_job()

    def run_and_clear(jid, sp, rn):
        run_pipeline(jid, source_path=str(sp), repo_name_override=rn)
        if rn in resources_cache:
            del resources_cache[rn]

    thread = threading.Thread(
        target=run_and_clear,
        args=(job_id, repo_path, name),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id, "repo_name": name}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    return job


@app.get("/repos")
def list_repos():
    """Return repos that have completed indexing (graph.pkl exists in artifacts/<name>/)."""
    if not ARTIFACTS_DIR.exists():
        return {"repos": []}
    repos = []
    for entry in sorted(ARTIFACTS_DIR.iterdir()):
        if entry.is_dir() and (entry / "graph.pkl").exists():
            repos.append(entry.name)
    return {"repos": repos}


# Hand-curated example questions for popular open-source Python repos.
# Anything not in this map gets a generic fallback. No LLM call on this path —
# that lets the frontend render examples instantly without burning tokens.
CURATED_EXAMPLES = {
    "fastapi": [
        "what breaks if I change OAuth2PasswordBearer?",
        "show me all code related to authentication",
        "where is dependency injection resolved?",
        "explain how routing works in fastapi",
    ],
    "flask": [
        "how does Flask's request context work?",
        "show me all routing logic",
        "what does the @app.route decorator actually do?",
        "where is the WSGI app entry point?",
    ],
    "django": [
        "how does the ORM resolve a query?",
        "show me all middleware classes",
        "where is URL routing handled?",
        "what breaks if I change the User model?",
    ],
    "requests": [
        "show me all authentication-related code",
        "what does HTTPBasicAuth do?",
        "how is session state managed?",
        "where are SSL settings configured?",
    ],
    "click": [
        "what does the @click.command decorator do?",
        "how is option parsing implemented?",
        "show me how command groups work",
        "what breaks if I change the Context class?",
    ],
    "httpx": [
        "how is connection pooling implemented?",
        "show me how async requests work",
        "where is HTTP/2 handled?",
        "what does the AsyncClient class do?",
    ],
}

GENERIC_EXAMPLES = [
    "give me a high-level overview of this codebase",
    "what are the main entry points?",
    "show me all authentication-related code",
    "how is configuration loaded?",
]


@app.get("/examples/{repo_name}")
def get_examples(repo_name: str):
    """Return suggested example questions for a repo. Curated for known repos, generic otherwise."""
    questions = CURATED_EXAMPLES.get(repo_name.lower(), GENERIC_EXAMPLES)
    return {"repo_name": repo_name, "questions": questions}