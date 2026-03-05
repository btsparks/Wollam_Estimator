"""Bid Chat page — per-bid AI chat with agent awareness."""

from nicegui import ui, run
from app.ui.layout import page_layout
from app.ui.components import page_header, empty_state
from app.ui import state
from app import query


# Module-level engine cache (keyed by bid_id)
_bid_engines = {}


def _get_bid_engine(bid_id: int):
    global _bid_engines
    if bid_id not in _bid_engines:
        try:
            from app.ai_engine import BidChatEngine
            engine = BidChatEngine(bid_id)
            # Load persisted history
            try:
                saved = query.get_chat_messages(bid_id)
                if saved:
                    engine.load_history([{"role": m["role"], "content": m["content"]} for m in saved])
            except Exception:
                pass
            _bid_engines[bid_id] = (engine, None)
        except (ValueError, Exception) as e:
            _bid_engines[bid_id] = (None, str(e))
    return _bid_engines[bid_id]


EXAMPLE_QUESTIONS = [
    "What does the spec say about HDPE pipe?",
    "What are the concrete strength requirements?",
    "Is there a retainage clause?",
    "What PPE is required beyond standard?",
    "What did the agents find?",
    "What are the top risks for this bid?",
]


@ui.page("/bid-chat")
async def bid_chat_page():
    state.set("current_path", "/bid-chat")
    page_layout("Bid Chat")

    with ui.column().classes("w-full nicegui-content").style("gap: 1rem"):
        page_header("Bid Chat", "Ask questions about bid documents, agent findings, and historical data")

        focus_bid = query.get_focus_bid()
        if not focus_bid:
            empty_state(
                "No focus bid set. Go to Active Bids and set a focus bid first.",
                icon="gavel",
                action_label="Active Bids",
                action_url="/active-bids",
            )
            return

        bid_id = focus_bid["id"]

        # Header
        ui.label(focus_bid["bid_name"]).classes("text-h6 text-grey-9 text-weight-bold")
        with ui.row().classes("flex-wrap").style("gap: 1rem"):
            if focus_bid.get("owner"):
                with ui.column().classes("gap-0"):
                    ui.label("Owner").classes("text-caption text-grey-6 uppercase")
                    ui.label(focus_bid["owner"]).classes("text-body2")
            if focus_bid.get("general_contractor"):
                with ui.column().classes("gap-0"):
                    ui.label("GC").classes("text-caption text-grey-6 uppercase")
                    ui.label(focus_bid["general_contractor"]).classes("text-body2")

            docs = query.get_bid_documents_list(bid_id)
            reports = query.get_agent_report_summaries(bid_id)

            with ui.column().classes("gap-0"):
                ui.label("Documents").classes("text-caption text-grey-6 uppercase")
                ui.label(str(len(docs))).classes("text-body2")
            with ui.column().classes("gap-0"):
                ui.label("Agent Reports").classes("text-caption text-grey-6 uppercase")
                ui.label(f"{len(reports)}/5").classes("text-body2")

        if not docs:
            empty_state("No documents uploaded yet.", icon="upload_file",
                        action_label="Active Bids", action_url="/active-bids")
            return

        ui.separator()

        # Engine setup
        engine, engine_error = _get_bid_engine(bid_id)

        if engine_error:
            with ui.card().classes("w-full bg-amber-1 q-pa-md"):
                ui.label(f"Chat unavailable: {engine_error}").classes("text-amber-9")
            return

        # Chat card
        with ui.card().classes("w-full"):
            # Messages container
            chat_key = f"bid_chat_{bid_id}"
            if state.get(chat_key) is None:
                # Load from DB
                try:
                    saved = query.get_chat_messages(bid_id)
                    state.set(chat_key, [
                        {"role": m["role"], "content": m["content"]} for m in saved
                    ])
                except Exception:
                    state.set(chat_key, [])

            messages = state.get(chat_key, [])

            chat_container = ui.column().classes("w-full overflow-y-auto").style(
                "gap: 0.5rem; max-height: 500px")

            with chat_container:
                for msg in messages:
                    is_user = msg["role"] == "user"
                    ui.chat_message(
                        text=msg["content"],
                        name="You" if is_user else "WEIS",
                        sent=is_user,
                    ).classes("chat-user" if is_user else "chat-assistant")

            # Example questions
            with ui.row().classes("w-full flex-wrap q-mt-sm").style("gap: 0.25rem"):
                extras = []
                if reports:
                    extras = [
                        "Drill deeper into the highest risk finding",
                        "What cost adders should we include?",
                    ]
                for ex in (EXAMPLE_QUESTIONS + extras)[:8]:
                    ui.button(ex, on_click=lambda q=ex: _send_bid_message(
                        q, bid_id, engine, chat_container, chat_key)) \
                        .props("flat dense size=sm color=primary no-caps") \
                        .classes("text-xs")

            # Input row
            with ui.row().classes("w-full items-center q-mt-sm").style("gap: 0.5rem"):
                chat_input = ui.input(
                    placeholder=f"Ask about {focus_bid['bid_name']} bid docs or agent findings..."
                ).classes("flex-grow")

                ui.button(icon="send", on_click=lambda: _send_bid_message(
                    chat_input.value, bid_id, engine, chat_container, chat_key, chat_input)) \
                    .props("round color=primary")

                chat_input.on("keydown.enter", lambda: _send_bid_message(
                    chat_input.value, bid_id, engine, chat_container, chat_key, chat_input))

            # Clear button
            def clear():
                query.clear_chat_messages(bid_id)
                state.set(chat_key, [])
                # Reset engine
                if bid_id in _bid_engines:
                    del _bid_engines[bid_id]
                ui.navigate.to("/bid-chat")

            ui.button("Clear Chat History", icon="delete_sweep", on_click=clear) \
                .props("flat color=negative size=sm").classes("q-mt-sm")


async def _send_bid_message(question, bid_id, engine, container, chat_key, input_el=None):
    if not question or not question.strip():
        return

    if input_el:
        input_el.value = ""

    # Store user message
    messages = state.get(chat_key, [])
    messages.append({"role": "user", "content": question})
    state.set(chat_key, messages)
    query.insert_chat_message(bid_id, "user", question)

    with container:
        ui.chat_message(text=question, name="You", sent=True).classes("chat-user")

    # Spinner
    with container:
        spinner = ui.chat_message(name="WEIS", sent=False).classes("chat-assistant")
        with spinner:
            ui.spinner("dots", size="lg")

    # Get response
    try:
        response = await run.io_bound(engine.ask, question)
    except Exception as e:
        response = f"**Error:** {e}"

    container.remove(spinner)

    messages.append({"role": "assistant", "content": response})
    state.set(chat_key, messages)
    query.insert_chat_message(bid_id, "assistant", response)

    with container:
        ui.chat_message(text=response, name="WEIS", sent=False).classes("chat-assistant")
