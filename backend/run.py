"""Start the Jal Drishti server: python run.py  (then open http://localhost:8000/)"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Jal Drishti running at http://localhost:{port}/  (API docs at /docs). Press Ctrl+C to stop.")
    uvicorn.run("jal_drishti.api:app", host="127.0.0.1", port=port)
