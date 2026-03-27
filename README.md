# MemBridge AI

A minimal full-stack AI chat app powered by a local Llama 3.2 model via Ollama, featuring an extraction-based memory system.

**Stack:** React (Vite/TSX) + FastAPI + Ollama (llama3.2:3b)

---

## Prerequisites

Make sure you have these installed:

- [Node.js](https://nodejs.org/) (v18+)
- [Python](https://www.python.org/) (3.10+)
- [Ollama](https://ollama.com/download) (for local AI)

---

## Project Structure

```text
membridge-ai/
├── backend/
│   ├── main.py            # FastAPI app + Ollama integration
│   ├── memory.py          # Fact extraction logic (Income, Loan Types)
│   ├── requirements.txt   # Python dependencies
│   ├── data/
│   │   └── memory.json    # JSON storage for user profiles (Memory)
├── frontend/
│   ├── src/
│   │   ├── App.tsx        # Root component (Vite/React)
│   │   ├── components/
│   │   │   ├── Chat.jsx   # Chat UI
│   │   │   └── Sidebar.jsx # App Navigation/Sidebar
│   └── tsconfig.app.json  # Configured for .jsx mixed-mode support
└── README.md
```

---

## Setup & Run

Follow these steps in order. Open three separate terminals.

### 1. Ollama (AI Model Setup)

First, download and install Ollama. Then, run these commands to set up the model:

https://ollama.com/download

```bash
# Pull the model (approx 2GB)
ollama pull llama3.2:3b

# Run the model locally
ollama run llama3.2:3b
```

*Keep this terminal open while using the app.*

### 2. Backend (FastAPI)

Navigate to the `backend` directory, install dependencies, and start the server:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

*Server runs on:* [http://localhost:8000](http://localhost:8000)

### 3. Frontend (React + Vite)

Navigate to the `frontend` directory, install dependencies, and start the development server:

```bash
cd frontend
npm install
npm run dev
```

*Frontend runs on:* [http://localhost:5173](http://localhost:5173)

---

## Recent Features & Improvements

### 🧠 Intelligent Memory System
The assistant now extracts key information from user messages (using logic in `memory.py`) and stores them in `memory.json`. 
- **Fact Extraction:** Automatically detects income, existing loans, and co-applicant details.
- **Contextual Recall:** The assistant remembers your profile across conversations to provide personalized advice.

### 🔧 TypeScript Integration Fix
Updated the frontend configuration to support mixed `.tsx` and `.jsx` modules. 
- **Change:** Enabled `allowJs: true` in `tsconfig.app.json`.
- **Reason:** Allows `App.tsx` (TypeScript) to import native JSX components seamlessly.

---

## API Documentation

`POST /chat`

**Request:**
```json
{
  "message": "Hi, I earn $50,000 and want a home loan.",
  "customer_id": "user_123"
}
```

**Response:**
```json
{
  "response": "Hello! I've noted that you earn $50,000. Based on that, I can suggest several home loan options..."
}
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Ollama not responding` | Ensure `ollama run llama3.2:3b` is running in a terminal. |
| `Connection refused` | Make sure the backend (Uvicorn) is running on port 8000. |
| `CORS Error` | Ensure the frontend is on port 5173 (standard Vite development port). |
| `Implicit any` on imports | This is fixed! We enabled JavaScript support in the TypeScript config. |
