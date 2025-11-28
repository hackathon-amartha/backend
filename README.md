# Amartha Hackathon Backend

FastAPI backend with Gemini AI integration and Supabase database.

## Setup

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

### 5. Run the server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Server will be available at:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

## API Endpoints

Base URL: `/api/v1`

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat/send` | Send message (creates thread if no thread_id) |
| `GET` | `/chat/threads` | List user's threads |
| `GET` | `/chat/threads/{id}` | Get thread with messages |
| `DELETE` | `/chat/threads/{id}` | Delete thread |

### Send Message

**Endpoint:** `POST /api/v1/chat/send`

**Headers:**
```
Authorization: Bearer <supabase_access_token>
Content-Type: multipart/form-data
```

**Form Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User's message |
| `thread_id` | string | No | Existing thread ID |
| `audio` | file | No | Audio file (.wav) |

**SSE Response:**
```
data: {"type": "thread_created", "thread_id": "uuid"}  // only for new threads
data: {"type": "chunk", "content": "Hello"}
data: {"type": "chunk", "content": " world"}
data: {"type": "title_generated", "title": "Greeting"}  // only for new threads
data: {"type": "done", "content": "Hello world"}
```

## Project Structure

```
backend/
├── app/
│   ├── config.py          # AI system instruction
│   ├── database.py        # Supabase connection
│   ├── models/
│   │   └── thread.py      # Database models & SQL schema
│   ├── routers/
│   │   ├── chat.py        # Chat endpoints
│   │   └── item.py        # Item endpoints (example)
│   ├── schemas/
│   │   ├── chat.py        # Pydantic schemas for chat
│   │   └── item.py        # Pydantic schemas for items
│   └── services/
│       ├── gemini.py      # Gemini AI service
│       └── thread.py      # Thread database operations
├── main.py                # FastAPI app entry point
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
└── .env.example           # Environment variables template
```
