"""Ask WEIS page — Estimating Intelligence Assistant.

Upgraded from basic chatbot to intent-aware estimating assistant with
structured responses, tool routing, and progressive disclosure.
"""

from nicegui import ui, run, app
from app.ui.layout import page_layout
from app.ui.components import page_header
from app.ui import state
from app import query


# Module-level engine singleton
_engine = None
_engine_error = None


def _get_engine():
    global _engine, _engine_error
    if _engine is None and _engine_error is None:
        try:
            from app.ai_engine import QueryEngine
            _engine = QueryEngine()
        except (ValueError, Exception) as e:
            _engine_error = str(e)
    return _engine, _engine_error


# Example questions organized by intent type
EXAMPLE_QUESTIONS = {
    "benchmark": [
        "What's a typical MH/CY for excavation?",
        "What production rate should I use for wall formwork?",
        "Average MH/LF for 24-inch HDPE pipe?",
    ],
    "lookup": [
        "Show me all jobs with piping data",
        "What crew did we use for concrete pours on 8553?",
        "How many hours did we burn on earthwork last year?",
    ],
    "recommendation": [
        "What equipment do we typically need for earthwork?",
        "What crew should I carry for structural steel?",
        "What rate should I use for grouting?",
    ],
    "general": [
        "What data do you have?",
        "What jobs have the most timecard data?",
    ],
}

BID_EXAMPLE_QUESTIONS = [
    "What does the RFP say about concrete?",
    "What are the spec requirements for pipe supports?",
    "Summarize the bid scope",
]


WELCOME_MD = """\
**Welcome to Ask WEIS** — your estimating intelligence assistant.

I have access to Wollam's complete HeavyJob history:
- **197 jobs** with full timecard and cost code data
- **278K+ timecard rows** with trade codes (Foreman, Operator, Laborer, Welder, etc.)
- **196K+ equipment entries** across all projects
- **15K+ cost codes** with actual field production data

**What I can do:**
- **Benchmark rates** — "What's typical MH/CY for excavation?" (aggregated across all jobs)
- **Crew planning** — "What crew did we use for pipe installs?" (trade-level breakdown)
- **Equipment analysis** — "What equipment for earthwork on 8553?"
- **Production trends** — "How did production ramp up on that job?"
- **Job comparison** — "Compare excavation rates on 8553 vs 8465"
- **Recommendations** — "What rate should I carry for formwork?" (with confidence + risk)

Try one of the examples below, or just ask.\
"""


@ui.page("/ask-weis")
def ask_weis_page():
    state.set("current_path", "/ask-weis")
    page_layout("Ask WEIS")

    # Use user storage for chat messages (survives async callbacks)
    if "weis_messages" not in app.storage.user:
        app.storage.user["weis_messages"] = []
    messages = app.storage.user["weis_messages"]

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header(
            "Ask WEIS",
            "Estimating intelligence assistant — rates, crews, equipment, production, and historical data"
        )

        # Engine check
        engine, engine_error = _get_engine()

        if engine_error:
            with ui.card().classes("w-full bg-amber-1 q-pa-md"):
                ui.label("API key not configured").classes("text-weight-bold")
                ui.label("Chat requires an Anthropic API key. "
                         "Copy .env.example to .env and add ANTHROPIC_API_KEY.").classes("text-body2")

        # Chat area
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Chat").classes("text-h6 text-weight-bold")
                with ui.row().classes("items-center").style("gap: 0.5rem"):
                    # Query stats badge
                    stats_label = ui.label("").classes("text-caption text-grey-6")
                    _update_stats_label(stats_label)
                    ui.button("Clear", icon="delete_sweep",
                              on_click=lambda: _clear_chat(chat_container, messages, stats_label)) \
                        .props("flat dense size=sm color=grey-7 no-caps")

            # Chat messages container
            chat_container = ui.column().classes("w-full overflow-y-auto").style(
                "gap: 0.75rem; max-height: 600px; scroll-behavior: smooth")

            with chat_container:
                if not messages:
                    _render_welcome()
                else:
                    _render_messages(messages)

            # Example questions — organized by intent
            focus = query.get_focus_bid() if engine else None
            with ui.column().classes("w-full q-mt-sm").style("gap: 0.25rem"):
                if focus:
                    with ui.row().classes("w-full flex-wrap").style("gap: 0.25rem"):
                        for ex in BID_EXAMPLE_QUESTIONS:
                            ui.button(ex,
                                      on_click=_make_send_handler(ex, chat_container, messages, stats_label)) \
                                .props("flat dense size=sm color=deep-purple no-caps") \
                                .classes("text-xs")

                # Flatten examples and show a mix
                all_examples = []
                for category, questions in EXAMPLE_QUESTIONS.items():
                    for q in questions:
                        all_examples.append((category, q))

                with ui.row().classes("w-full flex-wrap").style("gap: 0.25rem"):
                    for category, ex in all_examples[:8]:
                        color = {
                            "benchmark": "primary",
                            "lookup": "teal",
                            "recommendation": "orange",
                            "general": "grey-7",
                        }.get(category, "primary")
                        ui.button(ex,
                                  on_click=_make_send_handler(ex, chat_container, messages, stats_label)) \
                            .props(f"flat dense size=sm color={color} no-caps") \
                            .classes("text-xs")

            # Input row
            with ui.row().classes("w-full items-center q-mt-sm").style("gap: 0.5rem"):
                chat_input = ui.input(placeholder="Ask about rates, crews, equipment, production, comparisons...") \
                    .classes("flex-grow") \
                    .props('clearable')

                async def on_send_click():
                    question = chat_input.value
                    if not question or not question.strip():
                        return
                    chat_input.value = ""
                    await _send_message(question, chat_container, messages, stats_label)

                ui.button(icon="send", on_click=on_send_click) \
                    .props("round color=primary")
                chat_input.on("keydown.enter", on_send_click)


def _make_send_handler(question, container, messages, stats_label):
    """Create an async click handler for an example question button."""
    async def handler():
        await _send_message(question, container, messages, stats_label)
    return handler


def _render_welcome():
    """Render the welcome message with capabilities overview."""
    with ui.card().classes("w-full bg-blue-1 q-pa-md"):
        ui.markdown(WELCOME_MD).classes("text-body2")


def _render_messages(messages):
    for msg in messages:
        is_user = msg["role"] == "user"
        if is_user:
            with ui.chat_message(name="You", sent=True).classes("chat-user"):
                ui.label(msg["content"])
        else:
            with ui.chat_message(name="WEIS", sent=False).classes("chat-assistant"):
                ui.markdown(msg["content"], extras=["tables"]).classes("text-body2")
                # Show metadata if available
                if msg.get("tools_used"):
                    tools_text = ", ".join(msg["tools_used"])
                    elapsed = msg.get("elapsed", "")
                    meta = f"Tools: {tools_text}"
                    if elapsed:
                        meta += f" | {elapsed}s"
                    ui.label(meta).classes("text-caption text-grey-5 q-mt-xs")


def _update_stats_label(label):
    """Update the session stats label."""
    engine, _ = _get_engine()
    if engine and engine.query_log:
        n = len(engine.query_log)
        label.text = f"{n} {'query' if n == 1 else 'queries'} this session"
    else:
        label.text = ""


def _clear_chat(container, messages, stats_label):
    engine, _ = _get_engine()
    if engine:
        engine.reset()
    messages.clear()
    container.clear()
    with container:
        _render_welcome()
    _update_stats_label(stats_label)


async def _send_message(question: str, container, messages, stats_label):
    engine, engine_error = _get_engine()
    if not engine:
        ui.notify(f"Chat unavailable: {engine_error}", type="negative")
        return

    # Store user message
    messages.append({"role": "user", "content": question})

    # Render user message
    with container:
        with ui.chat_message(name="You", sent=True).classes("chat-user"):
            ui.label(question)

    # Show spinner
    with container:
        spinner = ui.chat_message(name="WEIS", sent=False).classes("chat-assistant")
        with spinner:
            with ui.row().classes("items-center").style("gap: 0.5rem"):
                ui.spinner("dots", size="lg")
                ui.label("Analyzing...").classes("text-caption text-grey-6")

    # Get AI response in thread pool
    try:
        response = await run.io_bound(engine.ask, question)
    except Exception as e:
        response = f"### Error\n{e}"

    # Get metadata from the latest query log entry
    tools_used = []
    elapsed = ""
    if engine.query_log:
        last = engine.query_log[-1]
        tools_used = last.get("tools_used", [])
        elapsed = str(last.get("elapsed_seconds", ""))

    # Remove spinner, render response
    container.remove(spinner)
    msg_data = {"role": "assistant", "content": response}
    if tools_used:
        msg_data["tools_used"] = tools_used
    if elapsed:
        msg_data["elapsed"] = elapsed
    messages.append(msg_data)

    with container:
        with ui.chat_message(name="WEIS", sent=False).classes("chat-assistant"):
            ui.markdown(response, extras=["tables"]).classes("text-body2")
            if tools_used:
                tools_text = ", ".join(tools_used)
                meta = f"Tools: {tools_text}"
                if elapsed:
                    meta += f" | {elapsed}s"
                ui.label(meta).classes("text-caption text-grey-5 q-mt-xs")

    _update_stats_label(stats_label)
