"""WEIS Active Bids — Create bids, upload documents, manage focus bid."""

import sys
from pathlib import Path

# Ensure project root on sys.path for Streamlit page discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from app import query
from app.doc_processing import extract_document, chunk_text
from app.database import init_db, get_connection

st.set_page_config(
    page_title="WEIS — Active Bids",
    page_icon="📋",
    layout="wide",
)


def _ensure_bid_tables():
    """Make sure the bid tables exist (idempotent)."""
    conn = get_connection()
    try:
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "active_bids" not in tables:
            init_db()
    finally:
        conn.close()


_ensure_bid_tables()

st.title("Active Bids")
st.caption("Manage active bids, upload bid documents (RFPs, specs, addenda), and set the focus bid")

# ---------------------------------------------------------------------------
# Create New Bid
# ---------------------------------------------------------------------------

with st.expander("Create New Bid", expanded=False):
    with st.form("create_bid_form"):
        col1, col2 = st.columns(2)
        with col1:
            bid_name = st.text_input("Bid Name *", placeholder="e.g., Acme Industrial Expansion")
            bid_number = st.text_input("Bid Number", placeholder="e.g., 8610")
            owner = st.text_input("Owner", placeholder="e.g., Acme Corp")
            general_contractor = st.text_input("General Contractor", placeholder="e.g., Kiewit")
        with col2:
            bid_date = st.date_input("Bid Date", value=None)
            project_type = st.text_input("Project Type", placeholder="e.g., Industrial, Commercial")
            location = st.text_input("Location", placeholder="e.g., Salt Lake City, UT")
            estimated_value = st.number_input("Estimated Value ($)", min_value=0.0, value=0.0, step=100000.0)

        notes = st.text_area("Notes", placeholder="Optional notes about this bid...")

        if st.form_submit_button("Create Bid", type="primary", use_container_width=True):
            if not bid_name:
                st.error("Bid name is required.")
            else:
                bid_id = query.create_active_bid(
                    bid_name=bid_name,
                    bid_number=bid_number or None,
                    owner=owner or None,
                    general_contractor=general_contractor or None,
                    bid_date=str(bid_date) if bid_date else None,
                    project_type=project_type or None,
                    location=location or None,
                    estimated_value=estimated_value if estimated_value > 0 else None,
                    notes=notes or None,
                )
                st.success(f"Created bid: **{bid_name}** (ID: {bid_id})")
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Bid Cards
# ---------------------------------------------------------------------------

try:
    bids = query.get_active_bids()
except Exception as e:
    st.error(f"Could not load bids: {e}")
    st.info("Try restarting the app — the database may need to be migrated.")
    st.stop()

if not bids:
    st.info("No active bids yet. Create one above to get started.")
    st.stop()

st.markdown(f"### {len(bids)} Active Bid{'s' if len(bids) != 1 else ''}")

for bid in bids:
    bid_id = bid["id"]
    is_focus = bid.get("is_focus", False)

    # Card header
    focus_badge = " 🎯" if is_focus else ""
    status_colors = {
        "active": "blue", "awarded": "green", "lost": "red",
        "no_bid": "gray", "archived": "gray",
    }
    status = bid.get("status", "active")
    status_color = status_colors.get(status, "gray")

    with st.expander(
        f"**{bid['bid_name']}**{focus_badge} — :{status_color}[{status.upper()}]",
        expanded=is_focus,
    ):
        # --- Metadata Row ---
        meta_cols = st.columns(5)
        if bid.get("owner"):
            meta_cols[0].markdown(f"**Owner:** {bid['owner']}")
        if bid.get("general_contractor"):
            meta_cols[1].markdown(f"**GC:** {bid['general_contractor']}")
        if bid.get("bid_date"):
            meta_cols[2].markdown(f"**Bid Date:** {bid['bid_date']}")
        if bid.get("estimated_value"):
            meta_cols[3].markdown(f"**Est. Value:** ${bid['estimated_value']:,.0f}")
        meta_cols[4].markdown(f"**Docs:** {bid.get('doc_count', 0)} ({bid.get('total_words', 0):,} words)")

        if bid.get("bid_number"):
            st.caption(f"Bid #{bid['bid_number']}")
        if bid.get("notes"):
            st.caption(bid["notes"])

        # --- Focus / Status Controls ---
        ctrl_cols = st.columns([2, 2, 2, 4])
        with ctrl_cols[0]:
            if is_focus:
                if st.button("Clear Focus", key=f"clear_focus_{bid_id}", use_container_width=True):
                    query.clear_focus_bid()
                    st.cache_resource.clear()
                    st.rerun()
            else:
                if st.button("Set as Focus", key=f"set_focus_{bid_id}", type="primary", use_container_width=True):
                    query.set_focus_bid(bid_id)
                    st.cache_resource.clear()
                    st.rerun()

        with ctrl_cols[1]:
            new_status = st.selectbox(
                "Status",
                ["active", "awarded", "lost", "no_bid", "archived"],
                index=["active", "awarded", "lost", "no_bid", "archived"].index(status),
                key=f"status_{bid_id}",
                label_visibility="collapsed",
            )
            if new_status != status:
                from app.database import get_connection
                conn = get_connection()
                try:
                    conn.execute(
                        "UPDATE active_bids SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (new_status, bid_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
                st.rerun()

        with ctrl_cols[2]:
            if st.button("Remove Bid", key=f"remove_{bid_id}", use_container_width=True):
                st.session_state[f"confirm_delete_{bid_id}"] = True

        # Confirm delete
        if st.session_state.get(f"confirm_delete_{bid_id}"):
            st.warning(f"Delete **{bid['bid_name']}** and all its documents? This cannot be undone.")
            del_cols = st.columns([2, 2, 6])
            with del_cols[0]:
                if st.button("Yes, Delete", key=f"confirm_yes_{bid_id}", type="primary"):
                    query.delete_bid_cascade(bid_id)
                    st.session_state.pop(f"confirm_delete_{bid_id}", None)
                    st.cache_resource.clear()
                    st.rerun()
            with del_cols[1]:
                if st.button("Cancel", key=f"confirm_no_{bid_id}"):
                    st.session_state.pop(f"confirm_delete_{bid_id}", None)
                    st.rerun()

        st.divider()

        # --- Document List ---
        docs = query.get_bid_documents(bid_id)

        if docs:
            st.markdown("**Documents:**")
            for doc in docs:
                ext_status = doc.get("extraction_status", "pending")
                icon = {"success": "🟢", "partial": "🟡", "failed": "🔴", "pending": "⏳"}.get(ext_status, "⏳")
                cat = doc.get("doc_category", "general")
                label = doc.get("doc_label", "")
                label_str = f" — {label}" if label else ""
                words = doc.get("word_count") or 0

                doc_cols = st.columns([6, 2, 2, 1])
                doc_cols[0].markdown(f"{icon} **{doc['filename']}** `[{cat}]`{label_str}")
                doc_cols[1].caption(f"{words:,} words")
                if doc.get("extraction_warning"):
                    doc_cols[2].caption(f"⚠ {doc['extraction_warning'][:50]}")
                with doc_cols[3]:
                    if st.button("🗑", key=f"del_doc_{doc['id']}", help="Delete document"):
                        query.delete_bid_document(doc["id"])
                        st.rerun()

        # --- Upload Documents ---
        st.markdown("**Upload Documents:**")
        upload_cols = st.columns([3, 2, 3])

        upload_counter = st.session_state.get(f"upload_counter_{bid_id}", 0)
        upload_key = f"upload_{bid_id}_{upload_counter}"

        with upload_cols[0]:
            uploaded_files = st.file_uploader(
                "Files",
                type=["pdf", "docx", "xlsx", "md", "txt"],
                accept_multiple_files=True,
                key=upload_key,
                label_visibility="collapsed",
            )

        with upload_cols[1]:
            doc_category = st.selectbox(
                "Category",
                ["general", "rfp", "addendum", "specification", "scope", "bid_form", "schedule"],
                key=f"cat_{bid_id}",
            )

        with upload_cols[2]:
            doc_label = st.text_input(
                "Label (optional)",
                placeholder="e.g., Division 03 Concrete",
                key=f"label_{bid_id}",
            )

        if uploaded_files:
            if st.button(
                f"Process {len(uploaded_files)} File{'s' if len(uploaded_files) != 1 else ''}",
                key=f"process_{bid_id}",
                type="primary",
                use_container_width=True,
            ):
                progress = st.progress(0, text="Processing documents...")

                for i, f in enumerate(uploaded_files):
                    progress.progress(
                        i / len(uploaded_files),
                        text=f"Processing {f.name}...",
                    )

                    file_bytes = f.read()
                    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else "txt"

                    # Extract text
                    result = extract_document(file_bytes, f.name)

                    # Insert document record
                    doc_id = query.insert_bid_document(
                        bid_id=bid_id,
                        filename=f.name,
                        file_type=ext,
                        file_size_bytes=len(file_bytes),
                        doc_category=doc_category,
                        doc_label=doc_label or None,
                        extraction_status=result["status"],
                        extraction_warning=result.get("warning"),
                        page_count=result.get("page_count"),
                        word_count=result["word_count"],
                    )

                    # Chunk and insert text if extraction succeeded
                    if result["status"] in ("success", "partial") and result["text"].strip():
                        chunks = chunk_text(result["text"])
                        if chunks:
                            query.insert_bid_chunks(doc_id, bid_id, chunks)

                progress.progress(1.0, text="Done!")
                st.success(f"Processed {len(uploaded_files)} file(s).")
                st.session_state[f"upload_counter_{bid_id}"] = upload_counter + 1
                st.cache_resource.clear()
                st.rerun()
