"""Ask WEIS page — Estimating Intelligence Assistant."""

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


EXAMPLE_QUESTIONS = [
    "What's a typical MH/CY for excavation?",
    "What production rate should I use for wall formwork?",
    "Show me all jobs with piping data",
    "What crew did we use for concrete pours on 8553?",
    "What lessons learned do we have for earthwork?",
    "What subcontractors have we used for rebar?",
]

BID_EXAMPLE_QUESTIONS = [
    "What does the RFP say about concrete?",
    "What are the spec requirements for pipe supports?",
    "Summarize the bid scope",
]


@ui.page("/ask-weis")
def ask_weis_page():
    state.set("current_path", "/ask-weis")
    page_layout("Ask WEIS")

    # Use user storage for chat messages (survives async callbacks)
    if "weis_messages" not in app.storage.user:
        app.storage.user["weis_messages"] = []
    messages = app.storage.user["weis_messages"]

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Ask WEIS", "Your estimating intelligence assistant — ask about rates, production, crews, and historical data")

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
                ui.button("Clear", icon="delete_sweep",
                          on_click=lambda: _clear_chat(chat_container, messages)) \
                    .props("flat dense size=sm color=grey-7 no-caps")

            # Chat messages container
            chat_container = ui.column().classes("w-full overflow-y-auto").style(
                "gap: 0.75rem; max-height: 600px; scroll-behavior: smooth")

            with chat_container:
                if not messages:
                    with ui.card().classes("w-full bg-blue-1 q-pa-md"):
                        ui.markdown(
                            "**Welcome to Ask WEIS.** I'm your estimating intelligence assistant. "
                            "I have access to 197 jobs, 15,000+ cost codes, and 221,000+ timecard rows "
                            "from Wollam's HeavyJob data.\n\n"
                            "Ask me about production rates, labor hours, crew data, materials, "
                            "subcontractors, or lessons learned. Try one of the examples below."
                        ).classes("text-body2")
                else:
                    _render_messages(messages)

            # Example questions
            focus = query.get_focus_bid() if engine else None
            with ui.row().classes("w-full flex-wrap q-mt-sm").style("gap: 0.25rem"):
                examples = (BID_EXAMPLE_QUESTIONS if focus else []) + EXAMPLE_QUESTIONS
                for ex in examples[:6]:
                    ui.button(ex,
                              on_click=_make_send_handler(ex, chat_container, messages)) \
                        .props("flat dense size=sm color=primary no-caps") \
                        .classes("text-xs")

            # Input row
            with ui.row().classes("w-full items-center q-mt-sm").style("gap: 0.5rem"):
                chat_input = ui.input(placeholder="Ask about rates, production, crews, materials, lessons learned...") \
                    .classes("flex-grow") \
                    .props('clearable')

                async def on_send_click():
                    question = chat_input.value
                    if not question or not question.strip():
                        return
                    chat_input.value = ""
                    await _send_message(question, chat_container, messages)

                ui.button(icon="send", on_click=on_send_click) \
                    .props("round color=primary")
                chat_input.on("keydown.enter", on_send_click)


def _make_send_handler(question, container, messages):
    """Create an async click handler for an example question button."""
    async def handler():
        await _send_message(question, container, messages)
    return handler


def _render_messages(messages):
    for msg in messages:
        is_user = msg["role"] == "user"
        if is_user:
            with ui.chat_message(name="You", sent=True).classes("chat-user"):
                ui.label(msg["content"])
        else:
            with ui.chat_message(name="WEIS", sent=False).classes("chat-assistant"):
                ui.markdown(msg["content"], extras=["tables"]).classes("text-body2")


def _clear_chat(container, messages):
    engine, _ = _get_engine()
    if engine:
        engine.reset()
    messages.clear()
    container.clear()
    with container:
        with ui.card().classes("w-full bg-blue-1 q-pa-md"):
            ui.markdown(
                "**Chat cleared.** Ask me anything about your historical job data."
            ).classes("text-body2")


async def _send_message(question: str, container, messages):
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
                ui.label("Querying data...").classes("text-caption text-grey-6")

    # Get AI response in thread pool
    try:
        response = await run.io_bound(engine.ask, question)
    except Exception as e:
        response = f"### Error\n{e}"

    # Remove spinner, render response
    container.remove(spinner)
    messages.append({"role": "assistant", "content": response})

    with container:
        with ui.chat_message(name="WEIS", sent=False).classes("chat-assistant"):
            ui.markdown(response, extras=["tables"]).classes("text-body2")
