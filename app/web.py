"""WEIS Streamlit Web Interface.

Browser-based chat UI that reuses the existing QueryEngine and query functions.
Run with: streamlit run app/web.py
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so "from app.x" imports work
# when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from app.ai_engine import QueryEngine
from app import query


# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="WEIS — Wollam Estimating Intelligence System",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "engine_error" not in st.session_state:
    st.session_state.engine_error = None


@st.cache_resource
def get_engine():
    """Create a shared QueryEngine instance (persists across reruns)."""
    try:
        return QueryEngine()
    except ValueError as e:
        return str(e)


def reset_conversation():
    """Clear chat history and reset engine conversation state."""
    st.session_state.messages = []
    engine = get_engine()
    if isinstance(engine, QueryEngine):
        engine.reset()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## WEIS")
    st.caption("Wollam Estimating Intelligence System")
    st.divider()

    # --- Database Status ---
    try:
        overview = query.get_database_overview()
        project_count = overview["record_counts"]["projects"]
        total_records = sum(overview["record_counts"].values())

        st.markdown("### Database Status")
        col1, col2 = st.columns(2)
        col1.metric("Projects", project_count)
        col2.metric("Total Records", f"{total_records:,}")

        # Record counts breakdown
        with st.expander("Record Counts"):
            for table, count in overview["record_counts"].items():
                label = table.replace("_", " ").title()
                st.markdown(f"- **{label}**: {count}")

    except Exception as e:
        st.error(f"Database error: {e}")
        overview = None

    st.divider()

    # --- Active Bids / Focus Bid ---
    try:
        active_bids = query.get_active_bids()
        if active_bids:
            st.markdown("### Active Bids")

            # Build options for the dropdown
            bid_options = {0: "None (no focus bid)"}
            for b in active_bids:
                label = b["bid_name"]
                if b.get("bid_number"):
                    label += f" (#{b['bid_number']})"
                bid_options[b["id"]] = label

            # Find current focus
            focus_bid = query.get_focus_bid()
            current_focus_id = focus_bid["id"] if focus_bid else 0
            bid_ids = list(bid_options.keys())
            current_index = bid_ids.index(current_focus_id) if current_focus_id in bid_ids else 0

            selected_bid_id = st.selectbox(
                "Focus Bid",
                bid_ids,
                index=current_index,
                format_func=lambda x: bid_options[x],
                key="focus_bid_selector",
            )

            # Update focus if changed
            if selected_bid_id != current_focus_id:
                if selected_bid_id == 0:
                    query.clear_focus_bid()
                else:
                    query.set_focus_bid(selected_bid_id)
                st.cache_resource.clear()
                st.rerun()

            # Show focus bid info
            if focus_bid:
                info_parts = []
                if focus_bid.get("owner"):
                    info_parts.append(f"Owner: {focus_bid['owner']}")
                if focus_bid.get("general_contractor"):
                    info_parts.append(f"GC: {focus_bid['general_contractor']}")
                if focus_bid.get("bid_date"):
                    info_parts.append(f"Bid: {focus_bid['bid_date']}")
                if info_parts:
                    st.caption(" · ".join(info_parts))

                # Doc count for focus bid
                bid_docs = query.get_bid_documents(focus_bid["id"])
                if bid_docs:
                    st.caption(f"{len(bid_docs)} document(s) uploaded")

            st.divider()
    except Exception:
        pass

    # --- Projects ---
    if overview and overview["projects"]:
        with st.expander("Projects", expanded=False):
            for proj in overview["projects"]:
                st.markdown(f"**Job {proj['job_number']}** — {proj['job_name']}")
                if proj.get("total_actual_cost"):
                    cost = proj["total_actual_cost"]
                    st.markdown(f"- Cost: ${cost:,.0f}")
                if proj.get("total_actual_mh"):
                    mh = proj["total_actual_mh"]
                    st.markdown(f"- Manhours: {mh:,.0f}")

    # --- Disciplines ---
    try:
        disciplines = query.get_discipline_summary()
        if disciplines:
            with st.expander("Disciplines", expanded=False):
                for d in disciplines:
                    code = d.get("discipline_code", "")
                    name = d.get("discipline_name", code)
                    budget = d.get("budget_cost") or 0
                    actual = d.get("actual_cost") or 0
                    variance = actual - budget
                    color = "red" if variance > 0 else "green"
                    st.markdown(
                        f"**{name}** (`{code}`)  \n"
                        f"Budget: ${budget:,.0f} · Actual: ${actual:,.0f} · "
                        f"Variance: :{color}[${variance:+,.0f}]"
                    )
    except Exception:
        pass

    st.divider()

    # --- Example Questions ---
    st.markdown("### Try These")

    # Bid-specific examples when a focus bid is set
    try:
        _focus = query.get_focus_bid()
    except Exception:
        _focus = None

    if _focus:
        bid_examples = [
            "What does the RFP say about concrete?",
            "What are the spec requirements for pipe supports?",
            "Summarize the bid scope",
            "Compare the RFP concrete scope to what we did on 8553",
        ]
        st.caption(f"**Bid: {_focus['bid_name']}**")
        for ex in bid_examples:
            if st.button(ex, key=f"bex_{ex[:20]}", use_container_width=True):
                st.session_state.pending_question = ex
        st.markdown("---")
        st.caption("**Historical:**")

    examples = [
        "What did we pay for 20-inch flanged joints?",
        "What was our concrete cost per CY?",
        "What crew did we use for mat pours?",
        "What was our GC percentage?",
        "What lessons did we learn about piping?",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex[:20]}", use_container_width=True):
            st.session_state.pending_question = ex

    st.divider()

    # --- Clear Conversation ---
    if st.button("Clear Conversation", use_container_width=True):
        reset_conversation()
        st.rerun()


# ---------------------------------------------------------------------------
# Main Chat Area
# ---------------------------------------------------------------------------

st.title("WEIS")
st.markdown("*Your estimating intelligence, built from your own job data.*")

# Quick KB stats banner if knowledge base has data
try:
    from app.database import get_connection as _get_conn
    _conn = _get_conn()
    try:
        _rl_count = _conn.execute("SELECT COUNT(*) as cnt FROM rate_library").fetchone()["cnt"]
        _jobs_count = _conn.execute(
            "SELECT COUNT(DISTINCT source_jobs) as cnt FROM rate_library WHERE source_jobs IS NOT NULL"
        ).fetchone()["cnt"]
        if _rl_count > 0:
            st.info(f"**{_rl_count} rates** from **{_jobs_count} job(s)** ready to use — ask anything below or browse the Knowledge Base page.")
    except Exception:
        pass
    finally:
        _conn.close()
except Exception:
    pass

# Check engine status
engine = get_engine()
engine_ok = isinstance(engine, QueryEngine)

if not engine_ok:
    st.warning(
        "**API key not configured.** Sidebar data is available, but chat requires "
        "an Anthropic API key.\n\n"
        "1. Copy `.env.example` to `.env`\n"
        "2. Add your `ANTHROPIC_API_KEY`\n"
        "3. Restart the app"
    )

# Replay chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle pending question from sidebar example buttons
pending = st.session_state.pop("pending_question", None)

# Chat input — context-aware placeholder
try:
    _chat_focus = query.get_focus_bid()
except Exception:
    _chat_focus = None

if _chat_focus:
    placeholder = f"Ask about {_chat_focus['bid_name']} bid docs or historical data..."
else:
    placeholder = "Ask a question about historical job cost data..."

user_input = st.chat_input(placeholder, disabled=not engine_ok)
question = pending or user_input

if question and engine_ok:
    # Display user message
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.messages.append({"role": "user", "content": question})

    # Get response with spinner
    with st.chat_message("assistant"):
        with st.spinner("Querying WEIS database..."):
            try:
                response = engine.ask(question)
            except Exception as e:
                response = f"**Error:** {e}"
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})

    # Force rerun to clear the input and show updated state
    st.rerun()
