# L'Écho: Shadowing Practice App

This repository contains the source code for L'Écho, a web application designed to help language learners compare their speech recordings against native reference audio.

^_^

## Setup & Installation

Follow these steps to set up the backend and frontend services locally.

### 1. Backend Server Setup

The backend is built with FastAPI and runs on Python 3.10+.

1.  Open your terminal and navigate to the backend directory:
    ```bash
    cd backend
    ```
2.  (Optional but recommended) Create and activate a Python virtual environment:
    ```bash
    python -m venv venv
    # On Windows (Command Prompt/Powershell):
    .\venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```
3.  Install Python dependencies listed in **[backend/requirements.txt](file:///c:/Users/Chiew%20Yuit%20Shuin%20Rya/Projects/lecho/backend/requirements.txt)**:
    ```bash
    pip install -r requirements.txt
    ```
4.  Run the development server using Uvicorn:
    ```bash
    uvicorn api.main:app --reload
    ```
    *   The API server will run at: `http://127.0.0.1:8000`
    *   Interactive API docs can be viewed at: `http://127.0.0.1:8000/docs`

---

### 2. Frontend Application Setup

The frontend is built using React, Vite, and CSS. It requires Node.js (v18+ recommended).

1.  Open a new terminal window and navigate to the frontend directory:
    ```bash
    cd frontend
    ```
2.  Install Javascript dependencies listed in **[frontend/package.json]**:
    ```bash
    npm install
    ```
3.  Start the local Vite development server:
    ```bash
    npm run dev
    ```
    *   The frontend application will be hosted at: `http://localhost:5173`

---

### 3. Backend layout

The backend is organized by role; `backend/` is the import root, so all commands
below run from `backend/` with the venv python.

| Folder | Contents |
| --- | --- |
| `api/` | FastAPI app, routers, request/response schemas, auth dependencies |
| `domain/` | Pure logic: the `dsp/` scoring package, content gate, job gates |
| `ingest/` | Bytes in → stored, validated, catalogued `AudioAsset` |
| `infra/` | SQLAlchemy models, engine/session, migrations, the storage seam |
| `worker/` | Transport-independent scoring orchestrator (`worker.core.run`) |
| `tools/` | Offline CLIs (seed, calibrate, native ingest, alignment) |
| `tests/` | Pytest suite — `pytest` from `backend/` |

Dependencies point one way: `api → domain, ingest, infra, worker`, `worker →
domain, infra`, `ingest → infra`, and `domain` imports nothing internal.

The scoring worker runs in-process via FastAPI `BackgroundTasks` today; Phase 3
swaps that dispatch for SQS without touching `worker.core.run`.

### 4. Offline tools

Run as modules so `backend/` stays the import root:

```bash
python -m tools.seed                     # reset + seed the dev database (destructive)
python -m tools.ingest_native <file.wav> --practice-id 3   # add a native reference clip
python -m tools.calibrate --smoke        # scoring harness on synthetic audio
python -m tools.align_natives            # word alignments (needs the `mfa` conda env)
```
