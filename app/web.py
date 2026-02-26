"""WEIS Streamlit Web Interface.

Browser-based chat UI that reuses the existing QueryEngine and query functions.
Run with: streamlit run app/web.py
"""

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
                if proj.get("cpi"):
                    st.markdown(f"- CPI: {proj['cpi']:.2f}")

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
st.caption("Wollam Estimating Intelligence System — Ask questions about historical job cost data")

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

# Chat input
user_input = st.chat_input("Ask a question about historical job cost data...", disabled=not engine_ok)
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
