# AI Sales Voice Agent

Real-time voice agent for sales conversations in English, Hindi and Hinglish.
Design: [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md).

**Current state: Phase 3** (voice conversation, answers from your documents, lead memory,
scoring and sentiment). Call summaries and the insights dashboard come in Phase 4.

## What Phase 1 does

- Browser voice call with live transcript
- Speech-to-text and text-to-speech through Sarvam, replies from Gemini 3.5 Flash-Lite
- Voice switches between English and Hindi with the caller
- Caller can interrupt the agent
- Per-turn latency shown on the page
- AI and transcription notice, consent check, call time limit

## What Phase 2 adds

- Upload PDF, DOCX, Markdown or text files on the web page
- Hybrid search (meaning and keywords) with a multilingual model running locally
- Passages are added to each question; the page shows which ones were used
- Questions with no matching passage are logged (`GET /knowledge-gaps`)

## What Phase 3 adds

- Lead facts (name, company, need, budget, authority, timeline, objections) collected live
- Rule-based score and Hot / Warm / Cold grade, with the caller's words as evidence
- Sentiment per turn, with a follow-up flag after repeated negative turns
- Memory: the agent knows what it has learned and summarises older parts of long calls
- Returning browsers are remembered by a random id; **Forget me** erases the data

Analysis runs in the background and can lag a turn or two. Transcripts are stored in
`data/leads.db` with card, ID, phone numbers and email addresses redacted.

Check qualification on scripted calls (billed Gemini requests):

```bash
.venv/bin/python -m scripts.eval_qualification
```

## Setup

Needs Python 3.12, Node.js 20.9 or newer, and a microphone.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
(cd apps/web && npm install)
cp .env.example .env
```

Fill in `.env`:

| Setting | Where to get it |
|---|---|
| `SARVAM_API_KEY` | https://dashboard.sarvam.ai |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | A free project at https://cloud.livekit.io, or a local server |

For a local LiveKit server instead of Cloud, install `livekit-server` from the
[official releases](https://github.com/livekit/livekit/releases) into a folder on your
`PATH` (such as `~/.local/bin`), or run `curl -sSL https://get.livekit.io | bash`.
The defaults in `.env.example` match the local server.

## Documents

Start the API, open the web page and upload files under **Product documents**.
`data/sample/` holds fictional documents for the demo company.

The first start downloads a 2.2 GB embedding model to `~/.cache/fastembed`.
Wait for `knowledge search is ready` in the API terminal before calling.

Measure retrieval quality (no API keys needed):

```bash
.venv/bin/python -m scripts.eval_retrieval
```

## Check latency first

```bash
.venv/bin/python -m scripts.benchmark --runs 5
```

This makes billed API calls and prints LLM and TTS latency for each language.

## Run

One command starts everything, including the local LiveKit server (Ctrl+C stops it):

```bash
bash scripts/start.sh
```

Or run each service in its own terminal, from the project root:

```bash
livekit-server --dev
.venv/bin/python -m apps.agent.main dev
.venv/bin/uvicorn apps.api.main:app --port 8000
cd apps/web && npm run dev
```

Open http://localhost:3000. Headphones give the cleanest interruption behaviour.

## Test a call without a microphone

With the services running, this places a real call using synthesized caller speech in
English, Hindi and Hinglish, including one interruption (billed requests):

```bash
.venv/bin/python -m scripts.simulate_call
```

The page's **Total** latency starts when the speech service reports the end of speech.
The caller waits longer than that; the simulated call measures the full wait.

## Test

```bash
.venv/bin/python -m pytest
```

The tests run offline and need no API keys. They do not cover live audio.

## Manual check for Phase 1

1. Start a call; the greeting plays.
2. Ask a question in English; the reply is in English.
3. Ask in Hindi, then in Hinglish; the reply and voice follow.
4. Say "haan" or "ok"; the language stays the same.
5. Interrupt a long reply; the agent stops and answers the new input.
6. Note the median **Total** latency (target: 1.5 s or less).

## Manual check for Phase 2

1. Upload both files from `data/sample/`.
2. Ask the price of the Growth plan in English, then ask about a discount in Hindi.
3. Ask something the documents do not cover; the agent should defer to a specialist.
4. Open http://localhost:8000/knowledge-gaps and find that question.

## Manual check for Phase 3

1. Say your name, company and problem; the lead panel updates.
2. Give your role, start date and monthly budget; the score rises.
3. Complain about the price twice in a row; the follow-up warning appears.
4. End the call and start another; the agent should not ask what it already knows.
5. Press **Forget me**; the next call starts from zero.

## Layout

```text
apps/agent/     voice worker (providers.py is the only vendor-specific module)
apps/api/       calls, room tokens, documents and search
apps/web/       call page and document upload
packages/core/  shared settings, knowledge search, lead scoring and storage
data/           sample documents; the SQLite databases are created here
evals/          retrieval questions and scripted sales calls
scripts/        latency benchmark and evaluations
tests/          offline tests
```

The API has no login or rate limit yet, so keep it on localhost.
