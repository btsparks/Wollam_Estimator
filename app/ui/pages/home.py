"""Home / Chat page — AI chat + KB stats."""

from nicegui import ui, run
from app.ui.layout import page_layout
from app.ui.components import page_header, metric_card
from app.ui import state
from app import query
from app.database import get_connection


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


def _get_kb_stats():
    try:
        conn = get_connection()
        try:
            rl = conn.execute("SELECT COUNT(*) as cnt FROM rate_library").fetchone()["cnt"]
            jobs = conn.execute(
                "SELECT COUNT(DISTINCT source_jobs) as cnt FROM rate_library WHERE source_jobs IS NOT NULL"
            ).fetchone()["cnt"]
            return rl, jobs
        finally:
            conn.close()
    except Exception:
        return 0, 0


EXAMPLE_QUESTIONS = [
    "What did we pay for 20-inch flanged joints?",
    "What was our concrete cost per CY?",
    "What crew did we use for mat pours?",
    "What was our GC percentage?",
    "What lessons did we learn about piping?",
]

BID_EXAMPLE_QUESTIONS = [
    "What does the RFP say about concrete?",
    "What are the spec requirements for pipe supports?",
    "Summarize the bid scope",
    "Compare the RFP concrete scope to what we did on 8553",
]


@ui.page("/")
@ui.page("/home")
async def home_page():
    state.set("current_path", "/home")
    page_layout("Home")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("WEIS", "Your estimating intelligence, built from your own job data.")

        # KB stats banner
        rl_count, jobs_count = _get_kb_stats()
        if rl_count > 0:
            ui.notification(
                f"{rl_count} rates from {jobs_count} job(s) ready to use",
                type="info", close_button=True, position="top",
            )

        # KPI row
        with ui.row().classes("w-full").style("gap: 1rem"):
            try:
                overview = query.get_database_overview()
                counts = overview.get("record_counts", {})
                with ui.column().classes("flex-1"):
                    metric_card("Projects", counts.get("projects", 0), icon="business")
                with ui.column().classes("flex-1"):
                    metric_card("Total Records", f"{sum(counts.values()):,}", icon="storage")
                with ui.column().classes("flex-1"):
                    metric_card("KB Rates", rl_count, icon="library_books")
                with ui.column().classes("flex-1"):
                    bids = query.get_active_bids()
                    metric_card("Active Bids", len(bids) if bids else 0, icon="gavel")
            except Exception:
                pass

        ui.separator()

        # Engine check
        engine, engine_error = _get_engine()

        if engine_error:
            with ui.card().classes("w-full bg-amber-1 q-pa-md"):
                ui.label("API key not configured").classes("text-weight-bold")
                ui.label("Chat requires an Anthropic API key. "
                         "Copy .env.example to .env and add ANTHROPIC_API_KEY.").classes("text-body2")

        # Chat area
        with ui.card().classes("w-full"):
            section_label = ui.label("Chat").classes("text-h6 text-weight-bold q-mb-sm")

            # Chat messages container
            chat_container = ui.column().classes("w-full overflow-y-auto").style(
                "gap: 0.5rem; max-height: 500px")

            messages = state.get("messages", [])
            with chat_container:
                _render_messages(messages)

            # Example questions
            focus = query.get_focus_bid() if engine else None
            with ui.row().classes("w-full flex-wrap q-mt-sm").style("gap: 0.25rem"):
                examples = (BID_EXAMPLE_QUESTIONS if focus else []) + EXAMPLE_QUESTIONS
                for ex in examples[:6]:
                    ui.button(ex, on_click=lambda q=ex: _send_message(q, chat_container)) \
                        .props("flat dense size=sm color=primary no-caps") \
                        .classes("text-xs")

            # Input
            with ui.row().classes("w-full items-center q-mt-sm").style("gap: 0.5rem"):
                chat_input = ui.input(placeholder="Ask a question about historical job cost data...") \
                    .classes("flex-grow")
                send_btn = ui.button(icon="send", on_click=lambda: _send_message(
                    chat_input.value, chat_container, chat_input)) \
                    .props("round color=primary")
                chat_input.on("keydown.enter", lambda: _send_message(
                    chat_input.value, chat_container, chat_input))


def _render_messages(messages):
    for msg in messages:
        is_user = msg["role"] == "user"
        with ui.chat_message(
            text=msg["content"],
            name="You" if is_user else "WEIS",
            sent=is_user,
        ).classes("chat-user" if is_user else "chat-assistant"):
            pass


async def _send_message(question: str, container, input_el=None):
    if not question or not question.strip():
        return

    engine, engine_error = _get_engine()
    if not engine:
        ui.notify(f"Chat unavailable: {engine_error}", type="negative")
        return

    # Clear input
    if input_el:
        input_el.value = ""

    # Store user message
    messages = state.get("messages", [])
    messages.append({"role": "user", "content": question})
    state.set("messages", messages)

    # Render user message
    with container:
        ui.chat_message(text=question, name="You", sent=True).classes("chat-user")

    # Show spinner
    with container:
        spinner = ui.chat_message(name="WEIS", sent=False).classes("chat-assistant")
        with spinner:
            loading = ui.spinner("dots", size="lg")

    # Get AI response in thread pool
    try:
        response = await run.io_bound(engine.ask, question)
    except Exception as e:
        response = f"**Error:** {e}"

    # Remove spinner, render response
    container.remove(spinner)
    messages.append({"role": "assistant", "content": response})
    state.set("messages", messages)

    with container:
        ui.chat_message(text=response, name="WEIS", sent=False).classes("chat-assistant")
