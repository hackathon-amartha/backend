# STT (Speech-to-Text) API Integration Guide

This guide explains how to integrate the STT endpoints from your frontend application.

## Base URL

```
http://localhost:8000/api/v1/stt
```

## Endpoints

### 1. Simple STT + LLM Response

**POST** `/stt/groq_simple`

Non-streaming endpoint that returns the complete response at once.

#### Request

- **Content-Type**: `multipart/form-data`
- **Body**:
  - `audio` (required): Audio/video file
  - `stt_model` (optional): STT model override
  - `llm_model` (optional): LLM model override

#### Response

```json
{
  "transcript": "User's spoken text",
  "llm_raw": { /* raw LLM response */ },
  "llm_text": "Assistant's reply text"
}
```

#### Frontend Example (JavaScript)

```javascript
async function sendAudio(audioBlob) {
  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');

  const response = await fetch('http://localhost:8000/api/v1/stt/groq_simple', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  console.log('Transcript:', data.transcript);
  console.log('LLM Response:', data.llm_text);
  return data;
}
```

---

### 2. Streaming STT + LLM Response (Recommended)

**POST** `/stt/groq_stream`

Returns Server-Sent Events (SSE) for real-time streaming response.

#### Request

- **Content-Type**: `multipart/form-data`
- **Body**:
  - `audio` (required): Audio/video file
  - `stt_model` (optional): STT model override
  - `llm_model` (optional): LLM model override

#### SSE Event Types

| Type | Description |
|------|-------------|
| `transcript` | The transcribed text from audio |
| `chunk` | Streaming chunk of LLM response |
| `done` | Final complete response |
| `error` | Error occurred |

#### Event Format

```
data: {"type": "transcript", "content": "User's spoken text"}

data: {"type": "chunk", "content": "Hello"}

data: {"type": "chunk", "content": ", how"}

data: {"type": "done", "content": "Hello, how can I help you?"}
```

#### Frontend Example (JavaScript)

```javascript
async function sendAudioStreaming(audioBlob, onTranscript, onChunk, onDone, onError) {
  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');

  const response = await fetch('http://localhost:8000/api/v1/stt/groq_stream', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6));

          switch (event.type) {
            case 'transcript':
              onTranscript?.(event.content);
              break;
            case 'chunk':
              onChunk?.(event.content);
              break;
            case 'done':
              onDone?.(event.content);
              break;
            case 'error':
              onError?.(event.content);
              break;
          }
        } catch (e) {
          console.error('Failed to parse SSE event:', e);
        }
      }
    }
  }
}

// Usage
sendAudioStreaming(
  audioBlob,
  (transcript) => console.log('Transcript:', transcript),
  (chunk) => process.stdout.write(chunk), // Append to UI
  (fullResponse) => console.log('\nComplete:', fullResponse),
  (error) => console.error('Error:', error)
);
```

---

## React Hook Example

```javascript
import { useState, useCallback } from 'react';

export function useSTT() {
  const [isLoading, setIsLoading] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [error, setError] = useState(null);

  const sendAudio = useCallback(async (audioBlob) => {
    setIsLoading(true);
    setTranscript('');
    setResponse('');
    setError(null);

    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');

    try {
      const res = await fetch('http://localhost:8000/api/v1/stt/groq_stream', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));

              switch (event.type) {
                case 'transcript':
                  setTranscript(event.content);
                  break;
                case 'chunk':
                  setResponse((prev) => prev + event.content);
                  break;
                case 'error':
                  setError(event.content);
                  break;
              }
            } catch (e) {
              console.error('Parse error:', e);
            }
          }
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { sendAudio, isLoading, transcript, response, error };
}
```

---

## Recording Audio Example

```javascript
let mediaRecorder;
let audioChunks = [];

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
  audioChunks = [];

  mediaRecorder.ondataavailable = (event) => {
    audioChunks.push(event.data);
  };

  mediaRecorder.start();
}

function stopRecording() {
  return new Promise((resolve) => {
    mediaRecorder.onstop = () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      resolve(audioBlob);
    };
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(track => track.stop());
  });
}

// Usage
await startRecording();
// ... user speaks ...
const audioBlob = await stopRecording();
await sendAudioStreaming(audioBlob, ...callbacks);
```

---

## Error Handling

| Status Code | Description |
|-------------|-------------|
| 400 | Invalid file type (must be audio/* or video/*) |
| 500 | API key not configured |
| 502 | Groq API error (STT or LLM) |

---

## Supported Audio Formats

- `audio/webm`
- `audio/wav`
- `audio/mp3`
- `audio/mpeg`
- `audio/ogg`
- `video/*` (audio will be extracted)

---

## CORS

Ensure your backend has CORS configured to accept requests from your frontend origin:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
