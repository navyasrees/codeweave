import sys
import os

# Ensure imports (bootstrap/indexer/etc.) resolve from the local project root.
# This avoids accidentally picking up a different `bootstrap.py` elsewhere in sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import bootstrap  # runs pipeline if needed

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.query_engine import load_resources, query

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

G, collection, model = load_resources()

class QueryRequest(BaseModel):
    question: str

@app.post("/query")
def handle_query(request: QueryRequest):
    result = query(request.question, G, collection, model)
    return {
        "answer": result["answer"],
        "mode": result["mode"],
        "node_count": result["node_count"],
    }