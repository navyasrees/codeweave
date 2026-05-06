import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
import threading
from pathlib import Path

# in-memory job store
jobs = {}

def create_job():
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "message": "Job created",
        "repo_name": None,
        "error": None,
    }
    return job_id

def update_job(job_id, status, message, repo_name=None, error=None):
    jobs[job_id]["status"] = status
    jobs[job_id]["message"] = message
    if repo_name:
        jobs[job_id]["repo_name"] = repo_name
    if error:
        jobs[job_id]["error"] = error

def get_job(job_id):
    return jobs.get(job_id)