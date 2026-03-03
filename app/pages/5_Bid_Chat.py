"""WEIS Bid Chat — Ask questions about bid documents and agent findings."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from app import query
from app.database import init_db, get_connection
from app.ai_engine import BidChatEngine

st.set_page_config(
    page_title="WEIS — Bid Chat",
    page_icon="💬",
    layout="wide",
)


def _ensure_tables():
    """Ensure bid_chat_messages table exists."""
    conn = get_connection()
    try:
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "bid_chat_messages" not in tables:
            init_db()
    finally:
        conn.close()


_ensure_tables()

st.title("Bid Chat")
st.caption("Ask questions about bid documents, agent findings, and historical data")

# ---------------------------------------------------------------------------
# Focus Bid Check
# ---------------------------------------------------------------------------

focus_bid = query.get_focus_bid()

if not focus_bid:
    st.warning("No focus bid set. Go to **Active Bids** and set a focus bid first.")
    st.stop()

bid_id = focus_bid["id"]

# Header
st.markdown(f"### {focus_bid['bid_name']}")
header_cols = st.columns(4)
if focus_bid.get("owner"):
    header_cols[0].metric("Owner", focus_bid["owner"])
if focus_bid.get("general_contractor"):
    header_cols[1].metric("GC", focus_bid["general_contractor"])

docs = query.get_bid_documents_list(bid_id)
header_cols[2].metric("Documents", len(docs))

# Show agent report status
reports = query.get_agent_report_summaries(bid_id)
completed_agents = len(reports)
header_cols[3].metric("Agent Reports", f"{completed_agents}/5")

if not docs:
    st.info("No documents uploaded yet. Upload bid documents on the **Active Bids** page first.")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Chat Engine Setup
# ---------------------------------------------------------------------------

# Initialize engine per bid (recreate if bid changes)
if "bid_chat_bid_id" not in st.session_state or st.session_state.bid_chat_bid_id != bid_id:
    st.session_state.bid_chat_bid_id = bid_id
    st.session_state.bid_chat_messages = []
    # Load persisted messages from DB
    try:
        saved = query.get_chat_messages(bid_id)
        st.session_state.bid_chat_messages = [
            {"role": m["role"], "content": m["content"]} for m in saved
        ]
    except Exception:
        pass

engine_error = None
try:
    engine = BidChatEngine(bid_id)
    # Load existing conversation into engine
    if st.session_state.bid_chat_messages:
        engine.load_history(st.session_state.bid_chat_messages)
except ValueError as e:
    engine = None
    engine_error = str(e)

if engine_error:
    st.warning(f"**Chat unavailable:** {engine_error}")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — Example Questions & Controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Bid Chat")
    st.caption(f"Asking about: **{focus_bid['bid_name']}**")
    st.divider()

    # Example questions
    st.markdown("**Try These:**")

    examples = [
        "What does the spec say about HDPE pipe?",
        "What are the concrete strength requirements?",
        "Is there a retainage clause?",
        "What PPE is required beyond standard?",
        "What did the agents find?",
        "What are the top risks for this bid?",
    ]

    if reports:
        examples.extend([
            "Drill deeper into the highest risk finding",
            "What cost adders should we include?",
        ])

    for ex in examples:
        if st.button(ex, key=f"chat_ex_{ex[:25]}", use_container_width=True):
            st.session_state.pending_chat_question = ex

    st.divider()

    if st.button("Clear Chat History", use_container_width=True):
        query.clear_chat_messages(bid_id)
        st.session_state.bid_chat_messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Chat Display
# ---------------------------------------------------------------------------

for msg in st.session_state.bid_chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle pending question from sidebar
pending = st.session_state.pop("pending_chat_question", None)

# Chat input
placeholder = f"Ask about {focus_bid['bid_name']} bid docs or agent findings..."
user_input = st.chat_input(placeholder, disabled=engine is None)
question = pending or user_input

if question and engine:
    # Display user message
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.bid_chat_messages.append({"role": "user", "content": question})
    query.insert_chat_message(bid_id, "user", question)

    # Get response
    with st.chat_message("assistant"):
        with st.spinner("Searching bid documents..."):
            try:
                response = engine.ask(question)
            except Exception as e:
                response = f"**Error:** {e}"
        st.markdown(response)

    st.session_state.bid_chat_messages.append({"role": "assistant", "content": response})
    query.insert_chat_message(bid_id, "assistant", response)
    st.rerun()
