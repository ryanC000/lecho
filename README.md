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
    uvicorn main:app --reload
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

### 3. Background Worker Run (Optional)

The backend runs a simulation worker internally, but you can also execute a standalone worker test run:

1.  Navigate to the worker directory:
    ```bash
    cd worker
    ```
2.  Execute the worker processor test script **[worker/main.py]**:
    ```bash
    python main.py
    ```
