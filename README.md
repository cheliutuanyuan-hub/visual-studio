# visual-studio

A **constrained e-commerce visual asset generation service** — not free-form
prompt-to-image, but a planner-driven pipeline that, given structured product
information (selling points + category spec + required/forbidden elements +
canvas), plans and produces a batch of reviewable candidate images with priority
queueing, provider routing, metadata quality checks, a structured event stream,
and restart recovery.

This is **Project B** of a two-project system. It is consumed over HTTP by
Project A's `VisualAgent` (see the API contract below). It is designed to be a
real, decoupled, production-shaped codebase — not a demo.

## Architecture (hexagonal / ports-and-adapters)

```
                          HTTP (FastAPI)
  Project A VisualAgent ────────────────┐
                                        ▼
   ┌────────────────────────────────────────────────────────────┐
   │  api layer (app.py, routers: health / generate / tasks)     │
   │      POST /v1/generate/batch  GET /v1/tasks/{id}            │
   │      GET /v1/events/stream (SSE)   GET /health              │
   └───────────────────────────┬────────────────────────────────┘
                               │ calls
   ┌───────────────────────────▼────────────────────────────────┐
   │  service / GenerationService  (application core)            │
   │    wires: planner + scheduler + providers + quality + bus   │
   └───┬───────────┬───────────────┬──────────────┬─────────────┘
       │           │               │              │
   ┌───▼───┐  ┌────▼─────┐   ┌─────▼──────┐  ┌────▼─────┐
   │Planner│  │Scheduler │   │Quality     │  │EventBus  │
   │(pure) │  │(priority │   │Checker     │  │pub/sub + │
   │       │  │ queue)   │   │(metadata)  │  │webhook   │
   └───────┘  └────┬─────┘   └────────────┘  └────┬─────┘
                   │                              │
          ┌────────▼─────────┐          ┌─────────▼──────────┐
          │ Persistence      │          │ (events persisted  │
          │ (SQLite, self-   │          │  to events table)  │
          │  initializing)   │          └────────────────────┘
          └────────┬─────────┘
                   │ behind a port
   ┌───────────────▼───────────────────────────────────────────┐
   │  ports.ImageProvider  (interface)                          │
   │   ├── MockProvider      (DEFAULT, writes real .svg files)  │
   │   ├── SeedreamProvider  (stub, NotImplementedError + notes)│
   │   └── GptImageProvider  (stub, NotImplementedError + notes)│
   └───────────────────────────────────────────────────────────┘
```

External systems (image generation backends, the webhook sink) sit strictly
behind interfaces. The default wiring uses a fully-functional **MockProvider**
that writes genuine SVG artifacts to disk, so the entire system runs **OFFLINE**
with no GPU, no docker and no network.

## Project layout

```
visual-studio/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── demo.py                  # root end-to-end check; prints VERIFICATION PASSED
├── tests/                   # pytest (planner, queue, provider, api)
└── src/visual_studio/
    ├── config.py            # pydantic-settings (VISUAL_* env)
    ├── logging_config.py
    ├── domain/              # models.py, contracts.py (pure)
    ├── ports/               # image_provider.py (abstract)
    ├── providers/           # mock.py (real), seedream.py / gpt_image.py (stubs)
    ├── planner/             # planner.py (deterministic)
    ├── quality/             # checker.py (metadata QA), alignment.py (0-1 scoring)
    ├── events/              # bus.py (pub/sub + optional webhook)
    ├── queue/               # scheduler.py (priority queue + reconcile)
    ├── persistence/         # sqlite.py (self-init schema)
    ├── service/             # generation_service.py (wiring)
    └── api/                 # app.py, schemas.py, routers/
```

## Setup

Requirements: Python 3.9+. All runtime deps are pure-Python and offline.

```bash
# from the project root
python -m pip install -r requirements.txt
python -m pip install pytest   # for the test suite
```

No environment is required for offline operation (defaults route everything to
the mock provider). See `.env.example` for every `VISUAL_*` variable.

## Run the service

```bash
# via module (reads VISUAL_* env / .env; defaults to port 8011)
python -m visual_studio

# or with explicit uvicorn
uvicorn visual_studio.api.app:create_app --factory --port 8011
```

The server starts a **background worker** that drains the priority queue, and on
startup runs **restart recovery** (re-enqueues any `queued`/`generating` task).

## API contract (consumed by Project A)

- `GET /health` → `{"status":"ok"}`

- `POST /v1/generate/batch` (202 Accepted)
  ```json
  {
    "case_id": "c1", "platform": "tmall",
    "category_spec": {"category":"kitchen",
      "canvas_presets":{"main":"800x800","scene":"1200x800","detail":"800x800"},
      "forbidden_terms":["最","第一"]},
    "selling_points":["便携","USB充电"],
    "images":[{"image_type":"main","canvas":"800x800","selling_point":"便携",
      "required_elements":["榨汁杯","水果"],"forbidden_elements":["文字logo"],
      "style_preset":"default"}]
  }
  ```
  Response: `{"batch_id":"...","task_ids":["..."],"status":"accepted"}`

- `GET /v1/tasks/{task_id}` →
  ```json
  {"task_id":"...","status":"succeeded","image_type":"main",
   "image_url":"/outputs/<task_id>.svg","carries_selling_point":"便携",
   "quality_flags":["required:榨汁杯","required:水果"],
   "alignment":{"score":1.0,"flags":["selling_point:carried"]},
   "provider":"mock","error":null}
  ```
  `status` ∈ `queued|generating|succeeded|failed`; `image_url` is `null` until
  succeeded. `alignment` is `null` until the artifact is scored. Generated
  artifacts are also served at `/outputs/...`.

- `GET /v1/events/stream?case_id=...` → SSE `data: {json}\n\n` lines for that
  case's events (`task.created`, `task.generating`, `task.succeeded`,
  `task.failed`).

### Content alignment (image <-> brief)

Alongside the structural `QualityChecker`, an `AlignmentChecker` scores every
succeeded artifact **0.0-1.0** on how much of the brief it actually carries:

- **coverage** — fraction of `required_elements` recorded as present in the
  artifact metadata (dominates the score);
- **selling point** — must appear in the prompt or recorded elements
  (`-0.3` otherwise);
- **forbidden leakage** — each forbidden term found in prompt/metadata costs
  `-0.2`.

The result (`alignment.score` + `alignment.flags`) is persisted and exposed in
the task contract for Project A's Critic to consume. Honest scope: like the
quality checker this is **metadata-grounded**, not pixel-level CV.

## Tests

```bash
python -m pytest -q
```

- `test_planner.py` — default plan yields main/scene/detail in descending
  priority; provided `images` are honoured; planner is deterministic.
- `test_queue.py` — highest-priority task dequeued first; FIFO tie-break;
  `reconcile_on_startup` resets `queued`/`generating` to `queued`.
- `test_provider.py` — `MockProvider` writes a real `.svg` containing prompt,
  required elements, canvas size and a `MOCK PROVIDER` label; records required
  elements as present.
- `test_api.py` — batch endpoint returns task ids; a task reaches `succeeded`
  via the background worker; the SVG exists on disk; the SSE stream emits
  structured events (exercised over a real uvicorn socket, since in-process
  TestClient/ASGI transports cannot handle an intentionally infinite SSE
  generator in current dependency versions).
- `test_alignment.py` — full coverage scores 1.0; missing required elements
  and missing selling points are penalized; `GET /v1/tasks/{id}` returns the
  alignment block end-to-end.

## End-to-end check

```bash
python demo.py
# -> VERIFICATION PASSED (exit 0)
```

## Honest limitations

- **MockProvider is the default and fully functional** (real SVG files on disk).
  The `SeedreamProvider` and `GptImageProvider` are **structured stubs** that
  raise `NotImplementedError` with exact endpoint + auth notes. They are wired
  behind the same port and selectable via `VISUAL_PROVIDER_ROUTE`, but they do
  **not** perform real generation in this build.
- **Quality checking and alignment scoring are metadata-level only.** They
  verify provider success, canvas-dimension match, required-element
  *recording*, forbidden-term absence, and selling-point carry-through. They
  are **not** pixel-level computer vision — they do not inspect the actual
  image content.
- **No GPU, no network, no docker required** for the default (mock) path. This
  is by design so the whole pipeline is reproducible and reviewable offline.
- The SSE endpoint uses a short poll interval over the persisted event log; it
  is correct but not a low-latency push transport.
