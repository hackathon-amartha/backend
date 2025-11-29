# Amartha Assist Backend

AI-powered customer service API for Amartha, providing intelligent chat assistance and speech-to-text capabilities.

## Overview

This backend powers the Amartha Assist chatbot, an AI customer service assistant trained to help users with:
- **Modal** - Microloan applications for women entrepreneurs (up to Rp30 million)
- **Celengan** - Investment products (5-8% annual returns, starting from Rp10,000)
- **AmarthaLink** - PPOB agent services (pulsa, bills, cash withdrawal)

The AI responds in the user's language (Indonesian, Sundanese, Javanese, etc.) with friendly, concise answers.

## Tech Stack

- **Framework**: FastAPI with async support
- **AI Models**: Google Gemini (chat), Groq Whisper (STT) + Llama (LLM)
- **Database**: Supabase (PostgreSQL)
- **Streaming**: Server-Sent Events (SSE) for real-time responses
- **Deployment**: Docker with Cloudflare Tunnel

## Quick Start (Docker)

```bash
# Copy environment file and configure
cp .env.example .env

# Start with Docker Compose
docker compose up --build
```

Server will be available at:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

## Manual Setup

### 1. Create virtual environment

```bash
python -m venv venv
```

### 2. Activate virtual environment

**Windows:**
```bash
venv\Scripts\activate
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:
- `GEMINI_API_KEY` - Google Gemini API key
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key (from Settings > API)
- `GROQ_API_KEY` - Groq API key (for STT/LLM)
- `CLOUDFLARE_TUNNEL_TOKEN` - Cloudflare Tunnel token (optional, for production)

### 5. Run the server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

Base URL: `/api/v1`

### Chat (Gemini AI)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat/send` | Send message with streaming response (creates thread if no thread_id) |
| `POST` | `/chat/threads` | Create a new thread |
| `GET` | `/chat/threads` | List user's threads |
| `GET` | `/chat/threads/{id}` | Get thread with messages |
| `GET` | `/chat/threads/{id}/messages` | Get all messages in a thread |
| `PATCH` | `/chat/threads/{id}` | Update thread title/system instruction |
| `DELETE` | `/chat/threads/{id}` | Delete thread |

### Speech-to-Text (Groq AI)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/stt/groq_simple` | Transcribe audio + LLM response (JSON) |
| `POST` | `/stt/groq_stream` | Transcribe audio + streaming LLM response (SSE) |

### Send Message (Chat)

**Endpoint:** `POST /api/v1/chat/send`

**Headers:**
```
Authorization: Bearer <supabase_access_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "message": "Hello",
  "thread_id": "uuid (optional)",
  "audio_base64": "base64-encoded audio (optional)"
}
```

**SSE Response:**
```
data: {"type": "thread_created", "thread_id": "uuid"}  // only for new threads
data: {"type": "chunk", "content": "Hello"}
data: {"type": "chunk", "content": " world"}
data: {"type": "title_generated", "title": "Greeting"}  // only for new threads
data: {"type": "done", "content": "Hello world"}
```

### STT Stream

**Endpoint:** `POST /api/v1/stt/groq_stream`

**Headers:**
```
Authorization: Bearer <supabase_access_token>
Content-Type: multipart/form-data
```

**Form Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio` | file | Yes | Audio file (audio/* or video/*) |
| `thread_id` | string | No | Existing thread ID |
| `stt_model` | string | No | Whisper model (default: whisper-large-v3) |
| `llm_model` | string | No | LLM model (default: llama-4-maverick) |

**SSE Response:**
```
data: {"type": "thread_created", "thread_id": "uuid"}  // only for new threads
data: {"type": "transcript", "content": "Transcribed text"}
data: {"type": "chunk", "content": "Response"}
data: {"type": "chunk", "content": " text"}
data: {"type": "title_generated", "title": "Thread Title"}  // only for new threads
data: {"type": "done", "content": "Full response text"}
```

## Docker

### Services

| Service | Description |
|---------|-------------|
| `backend` | FastAPI application on port 8000 |
| `cloudflared` | Cloudflare Tunnel for public exposure |

### Commands

```bash
# Start services
docker compose up

# Rebuild and start
docker compose up --build

# Stop services
docker compose down

# View logs
docker compose logs -f backend
```

## Project Structure

```
backend/
├── app/
│   ├── config.py          # AI system instruction (Gemini)
│   ├── database.py        # Supabase connection
│   ├── models/
│   │   └── thread.py      # Database models & SQL schema
│   ├── routers/
│   │   └── chat.py        # Chat endpoints
│   ├── schemas/
│   │   └── chat.py        # Pydantic schemas for chat
│   └── services/
│       ├── gemini.py      # Gemini AI service
│       ├── stt.py         # Groq STT/LLM service & endpoints
│       └── thread.py      # Thread database operations
├── main.py                # FastAPI app entry point
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Docker Compose configuration
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
└── .env.example           # Environment variables template
```
