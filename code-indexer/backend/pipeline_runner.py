import subprocess
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from indexer import index_repo
from graph_builder import build_graph, save_graph
from enricher import enrich_with_docs, enrich_with_tests
from embedder import embed_and_store
from detector import detect_structure
from backend.indexer_job import update_job
import json


# Resolve absolutely so the location is independent of shell cwd.
# This MUST match backend/main.py's ARTIFACTS_DIR — both files canonicalise
# to <project_root>/artifacts where project_root = code-indexer/.
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"


def run_pipeline(
    job_id: str,
    github_url: str = None,
    source_path: str = None,
    repo_name_override: str = None,
):
    """Run the indexing pipeline.

    Provide one of:
      - github_url: clone from GitHub, then index
      - source_path + repo_name_override: skip clone, index an already-on-disk folder
        (used by /index/upload after extracting a user-provided ZIP)
    """
    try:
        # Step 1 — get the source code on disk
        if github_url:
            update_job(job_id, "cloning", f"Cloning {github_url}...")
            repo_name = github_url.rstrip("/").split("/")[-1].replace(".git", "")
            repo_path = ARTIFACTS_DIR / repo_name / "repo"

            if repo_path.exists():
                shutil.rmtree(repo_path)
            repo_path.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                ["git", "clone", github_url, str(repo_path)],
                check=True,
                capture_output=True,
            )
        elif source_path:
            # Source already extracted to disk by the upload handler.
            update_job(job_id, "cloning", "Reading uploaded folder...")
            repo_path = Path(source_path)
            repo_name = repo_name_override or repo_path.parent.name
            if not repo_path.exists():
                raise FileNotFoundError(f"Uploaded source path does not exist: {repo_path}")
        else:
            raise ValueError("run_pipeline requires either github_url or source_path")

        # Step 2 — detect structure
        update_job(job_id, "detecting", "Detecting repo structure...")
        structure = detect_structure(repo_path)
        repo_name = structure["repo_name"]

        artifact_dir = ARTIFACTS_DIR / repo_name
        artifact_dir.mkdir(parents=True, exist_ok=True)

        if not structure["source_dir"]:
            update_job(job_id, "error", "Could not detect source directory", error="No source dir found")
            return

        # Step 3 — parse
        update_job(job_id, "parsing", "Parsing codebase...")
        indexed_functions, import_records = index_repo(structure["source_dir"])

        (artifact_dir / "indexed_functions.json").write_text(
            json.dumps(indexed_functions, indent=2)
        )
        (artifact_dir / "import_records.json").write_text(
            json.dumps(import_records, indent=2)
        )

        # Step 4 — build graph
        update_job(job_id, "building_graph", "Building context graph...")
        graph, name_index, _qualified_name_index = build_graph(indexed_functions, import_records)
        graph_file = artifact_dir / "graph.pkl"
        save_graph(graph, graph_file)

        # Step 5 — enrich
        update_job(job_id, "enriching", "Enriching nodes with docs and tests...")
        if structure["docs_dir"]:
            graph = enrich_with_docs(graph, structure["docs_dir"], name_index)
            save_graph(graph, graph_file)

        if structure["tests_dir"]:
            graph = enrich_with_tests(graph, structure["tests_dir"], name_index)
            save_graph(graph, graph_file)

        # Step 6 — embed
        update_job(job_id, "embedding", "Embedding nodes into vector store...")
        chroma_path = str(artifact_dir / "chroma")
        embed_and_store(graph_file, chroma_path, collection_name=repo_name)

        update_job(job_id, "done", "Indexing complete.", repo_name=repo_name)

    except Exception as e:
        update_job(job_id, "error", str(e), error=str(e))