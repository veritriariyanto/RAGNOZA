# streamlit_app/components/left_sidebar.py

from datetime import datetime, timedelta

import streamlit as st
from components.audio_controls import _inject_styles
from api.history.history_api import (
    get_all_history,
    update_history_title,
    delete_history,
)


# ── Date grouping helper ─────────────────────────────────────────────────────
def _group_by_date(histories: list) -> dict:
    """Group history items into: Today, Yesterday, Previous 7 Days, Older."""
    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    groups = {"Today": [], "Yesterday": [], "Previous 7 Days": [], "Older": []}

    for h in histories:
        created = h.get("created_at", "")
        try:
            dt = datetime.fromisoformat(str(created)).date()
        except (ValueError, TypeError):
            dt = None

        if dt is None:
            groups["Older"].append(h)
        elif dt == today:
            groups["Today"].append(h)
        elif dt == yesterday:
            groups["Yesterday"].append(h)
        elif dt > week_ago:
            groups["Previous 7 Days"].append(h)
        else:
            groups["Older"].append(h)

    return groups


def _format_time(created: str) -> str:
    """Extract just the time (HH:MM) from a datetime string."""
    try:
        dt = datetime.fromisoformat(str(created))
        return dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return ""


# ── Sidebar CSS ──────────────────────────────────────────────────────────────
_SIDEBAR_CSS = """
<style>
    /* Sidebar history item button styling */
    div[data-testid="stSidebar"] button[kind="secondary"] {
        text-align: left !important;
        padding: 6px 10px !important;
        line-height: 1.3 !important;
        font-size: 0.82rem !important;
        min-height: unset !important;
        border: none !important;
        background: transparent !important;
        border-radius: 8px !important;
    }
    div[data-testid="stSidebar"] button[kind="secondary"]:hover {
        background: rgba(255,255,255,0.06) !important;
    }
    div[data-testid="stSidebar"] .sidebar-group-label {
        font-size: 0.7rem;
        font-weight: 600;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 10px 4px 4px 4px;
        margin-top: 4px;
    }
    div[data-testid="stSidebar"] .sidebar-item-meta {
        font-size: 0.68rem;
        color: #6B6460;
        padding: 0 0 4px 8px;
    }
    div[data-testid="stSidebar"] .sidebar-empty {
        font-size: 0.78rem;
        color: #6B6460;
        text-align: center;
        padding: 20px 0;
    }
</style>
"""


def render_left_sidebar():
    _inject_styles()
    st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="ac-header">🧠 RAGNOZA</div>
        <div class="ac-subheader">AI Legal Assistant</div>
        """,
        unsafe_allow_html=True,
    )

    # ── Search ────────────────────────────────────────────────────────────────
    search_query = st.text_input(
        "Search", placeholder="🔍 Cari riwayat...", label_visibility="collapsed"
    )

    # ── Load / Refresh cache ──────────────────────────────────────────────────
    force_refresh = st.session_state.get("_force_refresh_history", False)

    if "_db_history_cache" not in st.session_state or force_refresh:
        st.session_state.pop("_force_refresh_history", None)
        resp = get_all_history()
        st.session_state["_db_history_cache"] = resp.get(
            "data", []) if resp else []

    db_histories = st.session_state.get("_db_history_cache", [])

    # ── Filter ────────────────────────────────────────────────────────────────
    if search_query:
        q = search_query.lower()
        filtered_db = [
            h for h in db_histories
            if q in (h.get("search_query") or "").lower()
            or q in (h.get("repaired_text") or "").lower()
            or q in (h.get("session_title") or "").lower()
        ]
    else:
        filtered_db = db_histories

    st.divider()

    # ── Empty state ───────────────────────────────────────────────────────────
    if not filtered_db:
        st.markdown(
            '<div class="sidebar-empty">Belum ada riwayat generate.</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Group by date ─────────────────────────────────────────────────────────
    groups = _group_by_date(filtered_db)

    for group_label in ["Today", "Yesterday", "Previous 7 Days", "Older"]:
        items = groups[group_label]
        if not items:
            continue

        st.markdown(
            f'<div class="sidebar-group-label">{group_label}</div>',
            unsafe_allow_html=True,
        )

        for h in items:
            title = (
                h.get("session_title")
                or h.get("search_query")
                or "Session Tanpa Judul"
            )
            # Truncate for display
            display_title = title[:45] + ("..." if len(title) > 45 else "")

            col_title, col_edit, col_del = st.columns(
                [7, 0.8, 0.8], vertical_alignment="center"
            )

            with col_title:
                if st.button(
                    display_title,
                    key=f"db_hist_{h['id']}",
                    use_container_width=True,
                ):
                    st.session_state["selected_history_id"] = h["id"]
                    st.session_state.current_session_id = None
                    st.session_state.pop("selected_history", None)
                    st.switch_page("pages/1_Hasil_Generate.py")

            with col_edit:
                if st.button(
                    "✏️",
                    key=f"edit_title_{h['id']}",
                    use_container_width=True,
                ):
                    st.session_state["editing_history_id"] = h["id"]

            with col_del:
                if st.button(
                    "🗑️",
                    key=f"del_hist_{h['id']}",
                    use_container_width=True,
                ):
                    if delete_history(h["id"]):
                        st.session_state.pop("_db_history_cache", None)
                        if st.session_state.get("selected_history_id") == h["id"]:
                            st.session_state.pop("selected_history_id", None)
                        st.rerun()

            # ── Inline edit form ──────────────────────────────────────────
            if st.session_state.get("editing_history_id") == h["id"]:
                new_title = st.text_input(
                    "Judul",
                    value=title,
                    key=f"title_input_{h['id']}",
                    label_visibility="collapsed",
                )
                save_col, cancel_col = st.columns(2)

                with save_col:
                    if st.button("💾", key=f"save_title_{h['id']}", use_container_width=True):
                        if update_history_title(h["id"], new_title.strip()):
                            st.session_state.pop("_db_history_cache", None)
                            st.session_state.pop("editing_history_id", None)
                            st.rerun()
                        else:
                            st.error("Gagal")

                with cancel_col:
                    if st.button("❌", key=f"cancel_title_{h['id']}", use_container_width=True):
                        st.session_state.pop("editing_history_id", None)
                        st.rerun()

    # ── Footer: session count ─────────────────────────────────────────────────
    st.markdown(
        f'<div class="sidebar-item-meta" style="padding-top:12px;border-top:1px solid rgba(255,255,255,0.08);margin-top:8px;">'
        f"{len(db_histories)} riwayat analisis</div>",
        unsafe_allow_html=True,
    )
