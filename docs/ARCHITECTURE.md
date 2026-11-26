# How the AI Sales Voice Agent Works

A detailed map of the system **as it is built today**: what is used, why, what it does and
how the parts connect. The scale-up design is in [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md).

## Visual overview

Colours: blue is the browser, purple is LiveKit, green is the voice agent, orange is an
external AI service, yellow is the API and grey is storage.

### System overview

![System overview: browser, LiveKit, voice agent, AI services, API and databases](diagrams/1-system-overview.svg)

### One conversation turn

![Eight steps from the caller speaking to hearing the reply, with background analysis](diagrams/2-conversation-turn.svg)

### Knowledge retrieval (RAG)

![Document indexing and question search with a similarity threshold](diagrams/3-knowledge-retrieval.svg)

### Lead qualification and sentiment

![From the caller's words to a rule-based score and grade](diagrams/4-lead-qualification.svg)

To change these images, edit [diagrams/build.py](diagrams/build.py) and run it again.
The sections below give the full detail.

## Contents

1. [The whole system](#1-the-whole-system)
2. [What we use and why](#2-what-we-use-and-why)
3. [Starting a call](#3-starting-a-call)
4. [One conversation turn](#4-one-conversation-turn)
5. [Interrupting the agent](#5-interrupting-the-agent)
6. [Choosing the language](#6-choosing-the-language)
7. [Knowledge retrieval (RAG)](#7-knowledge-retrieval-rag)
8. [Lead qualification and sentiment](#8-lead-qualification-and-sentiment)
9. [Memory](#9-memory)
10. [Ending a call](#10-ending-a-call)
11. [Stored data](#11-stored-data)
12. [Every connection](#12-every-connection)
13. [When something fails](#13-when-something-fails)
14. [Not built](#14-not-built)

## 1. The whole system

Solid arrows are used while the caller waits. Dotted arrows happen in the background.

```mermaid
flowchart TB
    subgraph Browser["Browser: Next.js web page, port 3000"]
        MIC["Microphone and speaker"]
        UI["Panels: transcript, lead, sources, latency"]
        DOCS["Document upload"]
    end

    LK["LiveKit server, port 7880<br/>carries audio and messages"]

    subgraph Worker["Voice agent worker (Python)"]
        VAD["Silero VAD<br/>hears interruptions"]
        SESSION["Agent session<br/>runs the pipeline"]
        ASSIST["Sales assistant<br/>language, memory, passages"]
        INTEL["Live intelligence<br/>analysis and scoring"]
        MEM["Conversation memory"]
    end

    subgraph Api["API server: FastAPI, port 8000"]
        CALLS["Calls and tokens"]
        KNOW["Documents and search"]
        EMB["E5 embedding model"]
    end

    subgraph Cloud["External AI services"]
        STT["Sarvam speech-to-text"]
        TTS["Sarvam text-to-speech"]
        GEM["Gemini: live reply"]
        GEMA["Gemini: analysis and summary"]
    end

    subgraph Data["Local databases (SQLite)"]
        KDB[("knowledge.db")]
        LDB[("leads.db")]
    end

    UI -->|"1. ask for a call"| CALLS
    CALLS -->|"2. room token"| UI
    MIC <-->|"3. live audio"| LK
    LK <--> SESSION
    SESSION --> VAD
    SESSION -->|caller audio| STT
    STT -->|text and language| SESSION
    SESSION --> ASSIST
    ASSIST -->|search question| KNOW
    KNOW --> EMB
    KNOW <--> KDB
    KNOW -->|passages| ASSIST
    ASSIST -->|prompt| GEM
    GEM -->|reply words| SESSION
    SESSION -->|reply text| TTS
    TTS -->|reply audio| SESSION
    LK -->|panel updates| UI
    DOCS --> KNOW

    SESSION -.->|each turn| INTEL
    INTEL -.-> GEMA
    ASSIST -.-> MEM
    MEM -.-> GEMA
    INTEL -.-> LDB
    INTEL -.->|facts and next question| ASSIST
    CALLS -.->|erase a lead| LDB
```

**In one sentence:** the browser sends the caller's voice through LiveKit to the agent,
which turns it into text, looks up the documents, asks Gemini for a reply and speaks it,
while a background task works out who the lead is and how interested they are.

## 2. What we use and why

### Services and libraries

| What we use | Purpose | What exactly it does here |
|---|---|---|
| **LiveKit server** | Real-time transport | Creates one room per call; carries audio both ways, transcripts and panel data |
| **LiveKit Agents** | Voice pipeline | Connects speech-to-text, model and speech; manages turns and interruptions |
| **Silero VAD** | Interruption detection | Runs locally and notices when the caller starts talking |
| **Sarvam `saaras:v4`** | Speech-to-text | Turns speech into text, detects the language and the end of speech |
| **Sarvam `bulbul:v4-flash`** | Text-to-speech | Speaks the reply with an English or Hindi voice setting |
| **Gemini 3.5 Flash-Lite** | Language model | Writes replies, extracts lead facts and sentiment, summarises long calls |
| **FastEmbed with `multilingual-e5-large`** | Embeddings | Turns text into vectors so a Hindi question can match English text |
| **FastAPI** | Backend API | Issues call tokens, manages documents, runs search, erases leads |
| **SQLite** | Storage | Holds documents, passages, vectors, leads, calls and transcripts |
| **Next.js and React** | Web page | Call controls, live panels and document upload |
| **Pydantic** | Validation | Checks settings, API input and the model's structured output |

### Our own code

| File | Role |
|---|---|
| [apps/agent/main.py](../apps/agent/main.py) | Builds the parts for each call and connects their events |
| [apps/agent/assistant.py](../apps/agent/assistant.py) | Greeting; prepares every turn with language, memory and passages |
| [apps/agent/providers.py](../apps/agent/providers.py) | The only place that chooses the speech and model vendors |
| [apps/agent/prompts.py](../apps/agent/prompts.py) | Instructions given to the model and fixed phrases |
| [apps/agent/language.py](../apps/agent/language.py) | Decides English, Hindi or Hinglish |
| [apps/agent/retrieval.py](../apps/agent/retrieval.py) | Asks the API for passages; skips small talk |
| [apps/agent/intelligence.py](../apps/agent/intelligence.py) | Background analysis queue, guidance and lead panel data |
| [apps/agent/memory.py](../apps/agent/memory.py) | Summarises older messages |
| [apps/agent/latency.py](../apps/agent/latency.py) | Converts timing measurements for the page |
| [apps/api/main.py](../apps/api/main.py) | Call tokens, health check, lead deletion |
| [apps/api/knowledge.py](../apps/api/knowledge.py) | Document and search endpoints |
| [packages/core/knowledge/](../packages/core/knowledge/) | Read, split, embed, store and search documents |
| [packages/core/leads/](../packages/core/leads/) | Fact schema, merge rules, scoring, redaction, storage |
| [packages/core/config.py](../packages/core/config.py) | All settings, read from `.env` |
| [apps/web/](../apps/web/) | The web page; `lib/useCall.ts` handles the live connection |

## 3. Starting a call

```mermaid
sequenceDiagram
    actor C as Caller
    participant W as Web page
    participant A as API
    participant L as LiveKit
    participant G as Agent worker
    participant D as leads.db

    Note over G,L: At startup the worker registers as sales-agent and each job process loads the VAD
    C->>W: Tick consent and press Start call
    W->>A: POST /calls with consent and saved lead id
    A->>A: Create room name and lead id if new
    A-->>W: Room URL, 10 minute token, lead id
    W->>L: Join the room and publish the microphone
    L->>G: Dispatch a job with the lead id
    G->>L: Connect to the room
    G->>D: Start the call record and load earlier facts
    D-->>G: Known facts for this lead
    G->>L: Send lead panel data
    G->>C: Spoken greeting with AI and transcription notice
    Note over G: A 10 minute call limit timer starts
```

The lead id is a random value kept in the browser. It is not a name or phone number.

## 4. One conversation turn

```mermaid
sequenceDiagram
    actor C as Caller
    participant G as Agent session
    participant S as Sarvam STT
    participant H as Sales assistant
    participant K as API search
    participant M as Gemini
    participant T as Sarvam TTS

    C->>G: Speech
    G->>S: Audio stream
    S-->>G: End of speech and transcript with language
    G->>H: Prepare the reply
    H->>H: Choose reply language
    H->>H: Drop messages already summarised
    alt Not small talk
        H->>K: Search the question, wait at most 0.8 s
        K-->>H: Up to 4 passages
    end
    H->>M: Instructions, history, summary, known facts, passages, language
    M-->>G: Reply words as they are generated
    G->>T: Text, sentence by sentence
    T-->>G: Audio
    G-->>C: Agent speaks
    Note over G,C: The page receives transcript, sources and timing
```

### What goes into the prompt

```mermaid
flowchart LR
    I["Fixed instructions<br/>persona, rules, honesty"] --> P["Request to Gemini"]
    H["Recent messages"] --> P
    S["Summary of older messages"] --> X["Context added to the<br/>latest caller message"]
    F["Known lead facts"] --> X
    N["One thing to ask next<br/>and mood warning"] --> X
    R["Document passages"] --> X
    L["Reply language"] --> X
    Q["Caller's words"] --> X
    X --> P
```

The added context is used for that request only and is not saved into the history.

## 5. Interrupting the agent

```mermaid
flowchart LR
    A["Agent is speaking"] --> B["Silero VAD hears the caller"]
    B --> C{"Speech lasts<br/>0.5 s or more?"}
    C -->|No| A
    C -->|Yes| D["Stop the voice and<br/>cancel the reply"]
    D --> E["Keep only the part<br/>that was spoken"]
    E --> F["Listen to the new question"]
```

LiveKit Agents handles these steps; our settings choose the detector and the 0.5 s limit.

## 6. Choosing the language

```mermaid
flowchart TB
    T["Caller's transcript"] --> R{"Asked for a language?<br/>e.g. Hindi please"}
    R -->|Yes| USE["Use the requested language"]
    R -->|No| S{"Which script and words?"}
    S -->|Devanagari only| HI["Hindi"]
    S -->|Devanagari and Latin| HG["Hinglish"]
    S -->|Latin with Hindi words| HG
    S -->|Latin, English words| EN["English"]
    S -->|Neither| KEEP["Keep the current language"]
    HI --> F{"Short reply after a<br/>language is established?"}
    HG --> F
    EN --> F
    F -->|Yes, under 3 words| KEEP
    F -->|No| SWITCH["Switch language"]
    USE --> V["Voice: en-IN for English,<br/>hi-IN for Hindi and Hinglish"]
    KEEP --> V
    SWITCH --> V
```

The same decision is written into the prompt, so the words and the voice agree.

## 7. Knowledge retrieval (RAG)

### Adding a document

```mermaid
flowchart LR
    U["Upload PDF, DOCX,<br/>Markdown or text"] --> V{"Under 5 MB and<br/>a supported type?"}
    V -->|No| E["Show an error"]
    V -->|Yes| P["Extract text"]
    P --> C["Split into passages of<br/>up to 220 words with headings"]
    C --> M["E5 model makes a<br/>vector for each passage"]
    M --> S[("knowledge.db<br/>text, vector, keyword index")]
```

Uploading a file with the same name replaces the earlier version.

### Searching

```mermaid
flowchart TB
    Q["Caller's question"] --> SHORT{"Five words or fewer?"}
    SHORT -->|Yes| ADD["Add the previous question"]
    SHORT -->|No| EMB
    ADD --> EMB["Make the question vector"]
    EMB --> V["Meaning search<br/>top 20 by similarity"]
    ADD --> K
    SHORT -->|No| K["Keyword search<br/>top 20 by BM25"]
    V --> F["Merge both rankings<br/>reciprocal rank fusion"]
    K --> F
    F --> TH{"Similarity 0.78<br/>or higher?"}
    TH -->|Yes| TOP["Keep the best 4"]
    TH -->|None pass| GAP{"Is it a question?"}
    TOP --> ANS["Gemini answers<br/>from the passages"]
    GAP -->|Yes| LOG["Log a knowledge gap"]
    TH -->|None pass| DEF["Agent must not invent facts<br/>and defers to a specialist"]
```

## 8. Lead qualification and sentiment

This runs in the background, so the caller never waits for it.

```mermaid
flowchart TB
    T["Caller turn"] --> Q["Queue<br/>waiting turns are grouped"]
    Q --> G["Gemini returns structured data:<br/>facts, evidence, objections, sentiment"]
    G -->|request fails| RT["Retry with the next turn"]
    RT --> Q
    G --> E{"Are the quoted words<br/>really in the caller's text?"}
    E -->|No| DROP["Reject that fact"]
    E -->|Yes| M["Merge with known facts<br/>keeping the more specific one"]
    M --> SC["Rules calculate the score"]
    G --> SE["Add the sentiment"]
    SE --> FL{"Two negative turns<br/>in a row?"}
    FL -->|Yes| FU["Flag for human follow-up"]
    SC --> DB[("leads.db<br/>sensitive numbers redacted")]
    FU --> DB
    SC --> PAGE["Update the lead panel"]
    SC --> NEXT["Pick the next missing fact<br/>for the agent to ask"]
    SE --> NEXT
```

The evidence check applies to need, budget, authority, timeline, name and company.

### Score rules

```mermaid
flowchart LR
    N["Need, up to 30<br/>specific 30, vague 15"] --> S["Total out of 100"]
    B["Budget, up to 25<br/>covers a plan 25<br/>no amount 10<br/>too low 5"] --> S
    A["Authority, up to 20<br/>decides or influences 20<br/>not involved 5"] --> S
    TL["Timeline, up to 25<br/>within 3 months 25<br/>3 to 6 months 15<br/>later or unclear 5"] --> S
    S --> H["70 or more: Hot"]
    S --> W["40 to 69: Warm"]
    S --> C["Below 40: Cold"]
```

An unknown fact scores 0. Sentiment is shown beside the score and does not change it.

## 9. Memory

```mermaid
flowchart TB
    subgraph During["During the call"]
        R["Recent messages<br/>12 kept word for word"]
        O{"6 or more older<br/>messages waiting?"}
        SUM["Gemini updates the summary<br/>in the background"]
        DROP["Summarised messages leave the prompt"]
        FACT["Lead facts"]
    end
    subgraph Across["Across calls"]
        DB[("leads.db: facts per lead id")]
        BR["Browser keeps the lead id"]
    end
    R --> O
    O -->|Yes| SUM
    SUM -->|success| DROP
    SUM -->|failure| R
    FACT --> DB
    BR -->|next call| DB
    DB -->|facts loaded| FACT
    F["Forget me button"] -->|delete| DB
    F -->|remove id| BR
```

The summary lasts only for the current call. Lead facts carry over to the next one.

## 10. Ending a call

```mermaid
flowchart LR
    A["Caller presses End call<br/>or the 10 minute limit is reached"] --> B["Stop timers and memory"]
    B --> C["Finish waiting analysis<br/>up to 7 seconds"]
    C --> D["Retry any failed turn once"]
    D --> E["Mark the call as ended"]
    E --> F["Close connections"]
```

No end-of-call summary is produced yet.

## 11. Stored data

```mermaid
erDiagram
    leads ||--o{ calls : has
    calls ||--o{ turns : contains
    documents ||--o{ chunks : "split into"

    leads {
        text id
        text tenant_id
        text facts
    }
    calls {
        text id
        text lead_id
        text consent_at
        text ended_at
        int score
        text grade
        int follow_up
    }
    turns {
        text id
        text call_id
        text speaker
        text text
        text language
        text sentiment
    }
    documents {
        int id
        text tenant_id
        text name
        text model
    }
    chunks {
        int id
        int document_id
        text content
        blob embedding
    }
    knowledge_gaps {
        int id
        text call_id
        text question
    }
```

`leads`, `calls` and `turns` are in `data/leads.db`. The others are in
`data/knowledge.db`, which also has a keyword index of the passages. Audio is not stored
by the app.

## 12. Every connection

| From | To | How | What is sent |
|---|---|---|---|
| Web page | API | HTTP | Consent, lead id, documents, delete requests |
| Web page | LiveKit | WebRTC | Microphone audio; receives agent audio |
| Agent | LiveKit | WebRTC | Agent audio, state and transcript |
| Agent | Web page, through LiveKit | Data messages `lead`, `sources`, `latency` | Panel updates |
| Agent | Sarvam | WebSocket | Caller audio, reply text |
| Agent | Gemini | HTTPS | Prompts, caller turns, summaries |
| Agent | API | HTTP `POST /search` | Search question and call id |
| Agent | `leads.db` | Direct file access | Calls, turns, facts, scores |
| API | `knowledge.db` | Direct file access | Documents, vectors, gaps |
| API | `leads.db` | Direct file access | Lead deletion |

**Leaves your computer:** audio and reply text go to Sarvam; prompts, including caller
words and document passages, go to Gemini. Embeddings are computed locally.

## 13. When something fails

| Failure | What happens |
|---|---|
| Document search is slow or down | The reply continues without passages; the agent should not claim facts |
| Lead analysis fails | The conversation continues; those turns are retried with the next one |
| Summary fails | The older messages stay in the prompt |
| Live reply model is overloaded | The library retries; the call may pause or stay silent |
| Panel message cannot be sent | It is ignored, usually because the call ended |
| A required key is missing | The agent stops at startup and names it |

## 14. Not built

| Feature | Note |
|---|---|
| End-of-call summary and business insights dashboard | Next planned phase |
| Appointment booking | Out of the current scope |
| CRM integration | Out of the current scope |
| Phone calls | Browser calls only |
| Login, roles and rate limits | Needed before any internet deployment |
