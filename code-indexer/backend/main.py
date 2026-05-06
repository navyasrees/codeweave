import sys
import os
import threading



# Ensure imports (bootstrap/indexer/etc.) resolve from the local project root.
# This avoids accidentally picking up a different `bootstrap.py` elsewhere in sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.query_engine import load_resources, query
from backend.indexer_job import create_job, get_job
from backend.pipeline_runner import run_pipeline


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
    thread = threading.Thread(
        target=run_pipeline,
        args=(job_id, request.github_url),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    return job