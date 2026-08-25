# ElevateBox Voice AI — Setup

Build for the ElevateBox SDE Intern assignment: an AI voice system that calls a
customer, sells e-commerce website development, qualifies the lead (Hot/Warm/Cold),
fires a mid-call message on high intent, books callbacks from spoken time, and
sends a post-call follow-up with context + resume.

## Project structure
```
elevatebox-voice-ai/
├── .env                  ← your real keys (never share this, never commit it)
├── .env.example           ← template, safe to share
├── requirements.txt
├── test_conversation.py   ← text-based conversation test harness (run this first)
├── test_telegram.py       ← standalone test for real Telegram sending
├── README.md
└── app/
    ├── __init__.py
    ├── lead_state.py       ← compact conversation state, tracked across turns
    ├── prompts.py          ← the sales agent's persona/system prompt
    ├── llm_engine.py        ← decision engine: one call per turn (Groq)
    ├── scheduler.py         ← spoken time → real datetime (also via Groq)
    ├── whatsapp.py           ← WhatsApp sender (stub mode by default) — the
    │                            actual required channel per the assignment
    └── telegram_msg.py       ← Telegram sender (stub mode by default) — free,
                                 instant-setup stand-in for dev/testing
```

## What's built so far
- **State tracking** that stays compact regardless of call length — no full
  transcript resent every turn, so latency doesn't creep up on a 5-6 min call
- **Decision engine** using Groq (free, no card required, fastest inference
  available — matters since the assignment calls out latency as a failure
  point), currently on model `openai/gpt-oss-120b` (Groq deprecated
  `llama-3.3-70b-versatile` in June 2026 — if you ever hit a `model_not_found`
  error again, check console.groq.com/docs/models for the current name)
- **Tool/function calling** for structured extraction: budget, product,
  timeline, features, barrier, classification (Hot/Warm/Cold), mid-call
  message trigger, and callback scheduling — all decided by the model in
  real time, not by keyword matching
- **Scheduler** that resolves natural phrases like "tomorrow morning" or
  "Friday around 5" into real datetimes using the LLM (a rules-based date
  parser was tried first and failed on exactly this kind of vague phrasing)
- **WhatsApp module** (`app/whatsapp.py`) — the assignment's actual required
  channel, in stub mode by default (prints instead of sends)
- **Telegram module** (`app/telegram_msg.py`) — same structure and stub-mode
  safety net as WhatsApp, but free and instant to set up (no business
  verification, no 24h token expiry). Useful for testing the messaging logic
  quickly during development; **switch to WhatsApp for the actual graded
  call**, since ElevateBox explicitly tests via WhatsApp

## Not built yet
- Twilio Media Streams (live phone audio in/out)
- Speech-to-text streaming (Deepgram)
- Text-to-speech streaming (ElevenLabs)
- Real WhatsApp sending (stubbed — flip on with `WHATSAPP_ENABLED=true` once
  Meta credentials are set up)
- Real callback booking to an actual calendar (currently just resolves +
  logs the datetime)

## Setup

```bash
cd elevatebox-voice-ai
python3 -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in at minimum:
```
GROQ_API_KEY=gsk_your_actual_key_here
YOUR_MOBILE_NUMBER=+91XXXXXXXXXX
```
Get a free Groq key at console.groq.com — no card required.

Everything else (Twilio, Deepgram, ElevenLabs, WhatsApp, Telegram, ngrok URL)
can stay blank for now — none of it is needed for the text-based test below.
`.env` is loaded automatically by both test scripts — no manual export needed.

## Run the conversation test

```bash
python test_conversation.py
```

This is a **text-only simulation** of the phone call — no audio, no real
phone involved yet. It's where we validate the conversation logic (discovery
flow, classification accuracy, when the mid-call action fires) before
spending time/money on live audio.

```
AI: Hi, this is Aditi calling from ElevateBox — hope I'm not catching you at a bad time?
You: _
```

Type as the customer, naturally. After each turn you'll see the live state:
```
--- current state ---
  classification : warm  (mentioned budget not decided, brother handles it)
  budget         : None
  product_type   : clothing (ethnic wear)
  ...
----------------------
```

Watch for:
- **Classification** updating as Hot / Warm / Cold based on what you say
- **`[WHATSAPP STUB]`** — the exact message that would be sent, when high
  intent is detected mid-call
- **`[CALLBACK SCHEDULED]`** — when you name a callback time, with the
  resolved datetime

Type `quit` to end — prints the full transcript, final classification, and
fires the post-call WhatsApp stub.

### A realistic test script

```
no its all good
yeah I run a small clothing store, mostly ethnic wear
not too sure honestly, maybe 150-200 items right now
budget is not really finalized yet, my brother actually handles the money side of things
ideally in the next month or so if things move fast
I'd want online payments and some way to track delivery status
haan actually ye sounds interesting, mujhe details chahiye
ok honestly how soon could you actually start if I say yes today
can you call me back tomorrow evening to finalize this
quit
```
This exercises discovery, a barrier (→ should classify `warm`, not `hot`),
a language switch, a hot signal (→ should trigger the WhatsApp stub), and
callback scheduling, all in one run.

## Test Telegram sending (optional, dev-only)

1. Message `@BotFather` on Telegram → `/newbot` → follow the two prompts
2. Copy the token → `TELEGRAM_BOT_TOKEN` in `.env`
3. Send your new bot any message first (bots can't message you first)
4. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser,
   find `"chat":{"id": ...}` → that's `TELEGRAM_CHAT_ID`
5. Set `TELEGRAM_ENABLED=true` in `.env`
6. Run:
   ```bash
   python test_telegram.py
   ```

## Known issues already fixed (for reference)
- **`GroqError: api_key must be set`** → `.env` wasn't being loaded; fixed by
  adding `load_dotenv()` at the top of the test scripts
- **`model_not_found` for `llama-3.3-70b-versatile`** → Groq deprecated it in
  June 2026; switched to `openai/gpt-oss-120b`
- **`tool_use_failed: expected string, but got null`** → the model sometimes
  sends `null` for fields with no new info instead of omitting them; fixed by
  allowing `null` in the tool schema and stripping null values before
  applying the update

## Next steps
1. Twilio Media Streams handler — real-time audio WebSocket
2. Deepgram streaming STT — turns live audio into text for `process_turn()`
3. ElevenLabs streaming TTS — turns `result["speech"]` into audio back to caller
4. Flip `WHATSAPP_ENABLED=true` once Meta credentials are ready (required for
   the actual graded call)
5. Live end-to-end test call
