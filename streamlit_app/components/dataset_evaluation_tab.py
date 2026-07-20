"""
streamlit_app/components/dataset_evaluation_tab.py

Dashboard Evaluasi Dataset (Golden Dataset):
 - Sub-tab 1: Kelola Dataset     — buat dataset baru, pilih dataset aktif, tambah item manual
 - Sub-tab 2: Upload Soal (CSV)  — unduh template, upload CSV bulk, preview isi dataset
 - Sub-tab 3: Jalankan & Hasil   — trigger run, polling status (manual/auto), lihat laporan agregat

Terpisah dari evaluation_ui.py (evaluasi per-request) karena domain data
dan siklus async-nya berbeda (lihat evaluation_dataset_api.py untuk detail).
"""

import time
import streamlit as st

from api.evaluasi.evaluation_dataset_api import (
    list_datasets,
    create_dataset,
    list_items,
    add_items,
    download_csv_template,
    upload_items_csv,
    trigger_run,
    list_runs,          # ← baru
    get_run_report,
)
from api.knowledge.knowledge_api import get_knowledgebase_list


# ─────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────

def _card_stat(value, label: str, color: str = "var(--text-primary)"):
    # Reuse class .kb-stat-card yang diinjeksi oleh knowledgebase_tab.py
    # (tab tersebut selalu dirender lebih dulu di app.py, jadi CSS ini
    # sudah tersedia di halaman saat dataset_evaluation_tab dirender).
    return (
        f'<div class="kb-stat-card">'
        f'<div class="kb-stat-value" style="color:{color};">{value}</div>'
        f'<div class="kb-stat-label">{label}</div>'
        f'</div>'
    )


def _get_dataset_options() -> list[dict]:
    with st.spinner("Memuat daftar dataset..."):
        res = list_datasets()
    if res.get("status") != "success":
        st.error(f"❌ Gagal memuat daftar dataset: {res.get('error')}")
        return []
    return res.get("data", [])


def _dataset_selectbox(key_suffix: str):
    """Selectbox dataset reusable — return (dataset_id, dataset_name) atau (None, None)."""
    datasets = _get_dataset_options()
    if not datasets:
        st.info("ℹ️ Belum ada dataset. Buat dataset baru terlebih dahulu di sub-tab **Kelola Dataset**.")
        return None, None

    labels = [f"{d['name']}  (#{d['id']} · {d['total_items']} soal)" for d in datasets]
    idx = st.selectbox(
        "Pilih Dataset", options=range(len(datasets)),
        format_func=lambda i: labels[i],
        key=f"ds_select_{key_suffix}",
    )
    selected = datasets[idx]
    return selected["id"], selected["name"]


# ─────────────────────────────────────────────────────────────────────────
# SUB-TAB 1: KELOLA DATASET
# ─────────────────────────────────────────────────────────────────────────

def _subtab_kelola():
    st.markdown('<div class="ac-label-step">BUAT DATASET BARU</div>', unsafe_allow_html=True)

    with st.form("form_create_dataset", clear_on_submit=True):
        name = st.text_input("Nama Dataset", placeholder="mis. golden-set-pidana-v1")
        desc = st.text_area("Deskripsi (opsional)", placeholder="Catatan singkat isi/tujuan dataset ini", height=80)
        submitted = st.form_submit_button("➕ Buat Dataset", type="primary")

    if submitted:
        if not name.strip():
            st.warning("⚠️ Nama dataset tidak boleh kosong.")
        else:
            with st.spinner("Membuat dataset..."):
                res = create_dataset(name.strip(), desc.strip() or None)
            if res.get("status") == "success":
                st.success(f"✅ Dataset '{name}' berhasil dibuat.")
                st.toast(f"Dataset '{name}' siap digunakan.", icon="✅")
                st.rerun()
            else:
                st.error(f"❌ Gagal membuat dataset: {res.get('error')}")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ac-label-step">TAMBAH SOAL MANUAL</div>', unsafe_allow_html=True)
    st.caption("Untuk banyak soal sekaligus, gunakan sub-tab **Upload Soal (CSV)** — lebih disarankan.")
    st.warning(
        "⚠️ **Keterbatasan saat ini:** soal yang ditambahkan lewat form manual di bawah ini "
        "belum menyimpan field Knowledge Base ke database (keterbatasan pada endpoint backend "
        "`POST /items`). Soal manual berisiko gagal saat dijalankan pada tahap 'Jalankan & Hasil'. "
        "Gunakan **Upload CSV** untuk hasil yang reliable.",
        icon="⚠️",
    )

    dataset_id, dataset_name = _dataset_selectbox("kelola")
    if dataset_id is None:
        return

    kb_list = get_knowledgebase_list()
    if not kb_list:
        st.warning("⚠️ Belum ada Knowledge Base tersedia. Soal butuh referensi collection Qdrant yang valid.")
        return

    with st.form("form_add_item", clear_on_submit=True):
        question = st.text_area("Pertanyaan / Skenario Hukum", height=100)
        ground_truth = st.text_area("Ground Truth (jawaban rujukan)", height=100)
        reference_context = st.text_area(
            "Reference Context (kutipan pasal rujukan, pisahkan antar-pasal dengan baris kosong)",
            height=120,
        )
        col_kb, col_cat = st.columns(2)
        with col_kb:
            knowledge_base = st.selectbox("Knowledge Base", options=kb_list)
        with col_cat:
            category = st.text_input("Kategori (opsional)", placeholder="mis. pidana, perdata")

        submitted_item = st.form_submit_button("➕ Tambah Soal", type="primary")

    if submitted_item:
        if not question.strip() or not ground_truth.strip() or not reference_context.strip():
            st.warning("⚠️ Pertanyaan, ground truth, dan reference context wajib diisi.")
        else:
            item = {
                "question": question.strip(),
                "ground_truth": ground_truth.strip(),
                "reference_context": reference_context.strip(),
                "category": category.strip() or None,
                "knowledge_base": knowledge_base,
            }
            with st.spinner("Menyimpan soal..."):
                res = add_items(dataset_id, [item])
            if res.get("status") == "success":
                st.success("✅ Soal berhasil ditambahkan.")
                st.toast("Soal baru tersimpan.", icon="✅")
                st.rerun()
            else:
                st.error(f"❌ Gagal menambah soal: {res.get('error')}")


# ─────────────────────────────────────────────────────────────────────────
# SUB-TAB 2: UPLOAD SOAL (CSV)
# ─────────────────────────────────────────────────────────────────────────

def _subtab_upload_csv():
    st.markdown('<div class="ac-label-step">UNDUH TEMPLATE CSV</div>', unsafe_allow_html=True)
    st.caption("Kolom wajib: `question, ground_truth, reference_context, knowledge_base` (+ `category` opsional).")

    tpl = download_csv_template()
    if tpl.get("status") == "success":
        st.download_button(
            "⬇️ Unduh Template CSV",
            data=tpl["content"],
            file_name="template_dataset_evaluasi.csv",
            mime="text/csv",
            key="btn_dl_template",
        )
    else:
        st.error(f"❌ Gagal mengunduh template: {tpl.get('error')}")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ac-label-step">UPLOAD SOAL DARI CSV</div>', unsafe_allow_html=True)

    dataset_id, dataset_name = _dataset_selectbox("upload_csv")
    if dataset_id is None:
        return

    uploaded_csv = st.file_uploader("Pilih file CSV", type=["csv"], key="ds_csv_uploader")
    if uploaded_csv is not None:
        if st.button("📤 Upload & Validasi", type="primary", key="btn_upload_csv"):
            with st.spinner("Mengunggah dan memvalidasi CSV..."):
                res = upload_items_csv(dataset_id, uploaded_csv.getvalue(), uploaded_csv.name)

            if res.get("status") != "success":
                st.error(f"❌ Upload gagal: {res.get('error')}")
                st.toast("Upload gagal diproses.", icon="❌")
            else:
                result = res["data"]
                inserted = result.get("inserted_count", 0)
                skipped = result.get("skipped_count", 0)
                errors = result.get("errors", [])

                # Notifikasi eksplisit bahwa proses upload sudah SELESAI diproses,
                # tidak hanya mengandalkan angka pada kartu statistik.
                if inserted > 0 and skipped == 0:
                    st.success(f"✅ Upload selesai diproses — {inserted} soal berhasil ditambahkan.")
                    st.toast(f"{inserted} soal berhasil ditambahkan.", icon="✅")
                elif inserted > 0 and skipped > 0:
                    st.warning(
                        f"⚠️ Upload selesai diproses dengan sebagian error — "
                        f"{inserted} berhasil, {skipped} dilewati. Lihat detail di bawah."
                    )
                    st.toast(f"Upload selesai: {inserted} berhasil, {skipped} dilewati.", icon="⚠️")
                else:
                    st.error("❌ Upload selesai diproses, tetapi tidak ada soal yang berhasil ditambahkan.")
                    st.toast("Tidak ada soal yang berhasil ditambahkan.", icon="❌")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(_card_stat(inserted, "Berhasil Ditambahkan", "var(--green)"), unsafe_allow_html=True)
                with col2:
                    zero_color = "var(--text-muted)" if skipped == 0 else "var(--orange)"
                    st.markdown(_card_stat(skipped, "Dilewati (Error)", zero_color), unsafe_allow_html=True)

                if errors:
                    with st.expander(f"⚠️ Detail {len(errors)} baris yang dilewati", expanded=True):
                        for err in errors:
                            st.warning(f"Baris {err['row_number']}: {err['reason']}")

                if inserted > 0:
                    st.session_state.pop("_ds_items_cache", None)

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ac-label-step">PREVIEW ISI DATASET</div>', unsafe_allow_html=True)

    with st.spinner("Memuat isi dataset..."):
        res_items = list_items(dataset_id)
    if res_items.get("status") != "success":
        st.error(f"❌ Gagal memuat item: {res_items.get('error')}")
        return

    items = res_items.get("data", [])
    if not items:
        st.info("ℹ️ Dataset ini belum punya soal.")
        return

    st.caption(f"Total {len(items)} soal dalam dataset '{dataset_name}'.")
    st.dataframe(
        [
            {
                "ID": it["id"],
                "Pertanyaan": (it["question"][:80] + "…") if len(it["question"]) > 80 else it["question"],
                "Kategori": it.get("category") or "-",
                "Dibuat": it["created_at"],
            }
            for it in items
        ],
        use_container_width=True,
        hide_index=True,
    )


# ─────────────────────────────────────────────────────────────────────────
# SUB-TAB 3: JALANKAN & HASIL
# ─────────────────────────────────────────────────────────────────────────

_METRIC_FIELDS = [
    ("faithfulness_summary", "Faithfulness (Summary)"),
    ("faithfulness_qa", "Faithfulness (QA)"),
    ("answer_relevancy", "Answer Relevancy"),
    ("context_precision", "Context Precision"),
    ("context_recall", "Context Recall"),
    ("risk_faithfulness", "Risk Faithfulness"),
]


def _render_metric_row(agg: dict, title: str):
    st.markdown(f"**{title}**")
    cols = st.columns(len(_METRIC_FIELDS))
    for col, (field, label) in zip(cols, _METRIC_FIELDS):
        val = agg.get(field)
        with col:
            st.metric(label, f"{val:.2f}" if val is not None else "N/A")


def _subtab_run():
    st.markdown('<div class="ac-label-step">JALANKAN EVALUASI DATASET</div>', unsafe_allow_html=True)

    dataset_id, dataset_name = _dataset_selectbox("run")
    if dataset_id is None:
        return

    col_label, col_btn = st.columns([3, 1], vertical_alignment="bottom")
    with col_label:
        label = st.text_input("Label Run (opsional)", placeholder="mis. baseline, prompt-v2", key="ds_run_label")
    with col_btn:
        if st.button("▶️ Jalankan", type="primary", use_container_width=True, key="btn_trigger_run"):
            with st.spinner("Memicu evaluasi (berjalan di background)..."):
                res = trigger_run(dataset_id, label.strip() or None)
            if res.get("status") == "success":
                run_data = res["data"]
                st.session_state["_dataset_eval_active_run_id"] = run_data["id"]
                st.success(f"✅ Run #{run_data['id']} dimulai — status: {run_data['status']}.")
                st.toast(f"Run #{run_data['id']} dimulai.", icon="▶️")
                st.rerun()
            else:
                st.error(f"❌ Gagal memulai run: {res.get('error')}")
                st.toast("Gagal memulai run.", icon="❌")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ac-label-step">STATUS & LAPORAN RUN</div>', unsafe_allow_html=True)

    with st.spinner("Memuat riwayat run..."):
        res_runs = list_runs(dataset_id)
    if res_runs.get("status") != "success":
        st.error(f"❌ Gagal memuat riwayat run: {res_runs.get('error')}")
        return

    runs = res_runs.get("data", [])
    if not runs:
        st.info("ℹ️ Belum ada run untuk dataset ini. Klik 'Jalankan' di atas untuk memulai.")
        return

    status_icon_map = {"pending": "🟡", "running": "🔵", "completed": "🟢", "failed": "🔴"}

    def _run_label(r: dict) -> str:
        icon = status_icon_map.get(r["status"], "⚪")
        label_part = f" · {r['label']}" if r.get("label") else ""
        return f"{icon} Run #{r['id']}{label_part} — {r['status']} — {r['triggered_at']}"

    active_run_id = st.session_state.get("_dataset_eval_active_run_id")
    default_idx = 0
    if active_run_id is not None:
        matching = [i for i, r in enumerate(runs) if r["id"] == active_run_id]
        if matching:
            default_idx = matching[0]

    run_idx = st.selectbox(
        "Pilih Run",
        options=range(len(runs)),
        format_func=lambda i: _run_label(runs[i]),
        index=default_idx,
        key="ds_run_select",
    )
    selected_run_id = runs[run_idx]["id"]

    # ── Auto-refresh toggle dengan VERSIONED KEY ─────────────────────────
    # Kita tidak pernah menulis langsung ke key widget toggle yang aktif
    # (itu yang menyebabkan StreamlitAPIException). Sebagai gantinya, saat
    # run selesai, kita naikkan nomor versi -> toggle di render berikutnya
    # akan punya key BARU yang belum pernah diinstansiasi, sehingga otomatis
    # kembali ke default (mati) tanpa melanggar aturan Streamlit.
    toggle_version = st.session_state.get("_dataset_eval_toggle_version", 0)
    toggle_key = f"_dataset_eval_auto_refresh_{toggle_version}"

    col_check, col_auto = st.columns([2, 2])
    with col_check:
        check_now = st.button("🔄 Refresh Status", use_container_width=True, key="btn_check_run")
    with col_auto:
        auto_refresh = st.toggle("🔁 Auto-refresh (5 detik)", key=toggle_key)

    with st.spinner("Memuat laporan run..."):
        res_report = get_run_report(selected_run_id)

    if res_report.get("status") != "success":
        st.error(f"❌ Gagal memuat laporan run: {res_report.get('error')}")
        return

    # Notifikasi eksplisit khusus saat user klik refresh manual, supaya user
    # tahu proses cek status sudah selesai (tidak dipakai saat auto-refresh
    # agar toast tidak muncul berulang setiap 5 detik).
    if check_now:
        st.toast("Status run diperbarui.", icon="🔄")

    report = res_report["data"]
    status = report["status"]

    st.markdown(f"### {status_icon_map.get(status, '⚪')} Run #{report['run_id']} — Status: `{status}`")
    st.caption(
        f"Dataset ID: {report['dataset_id']} | Label: {report.get('label') or '-'} | "
        f"Item diproses: {report['total_items']}"
    )

    if status in ("completed", "failed"):
        # Naikkan versi -> toggle "reset" ke OFF di render berikutnya,
        # tanpa pernah menyentuh key widget yang sedang aktif.
        st.session_state["_dataset_eval_toggle_version"] = toggle_version + 1
        if active_run_id == selected_run_id:
            st.session_state.pop("_dataset_eval_active_run_id", None)
            if status == "completed":
                st.toast(f"Run #{report['run_id']} selesai.", icon="✅")
            else:
                st.toast(f"Run #{report['run_id']} gagal.", icon="❌")

    if report["total_items"] == 0:
        st.info("⏳ Evaluasi sedang berjalan di background, belum ada hasil. Klik 'Refresh Status', atau aktifkan Auto-refresh.")
    else:
        if status == "completed":
            st.success(f"✅ Run #{report['run_id']} selesai — {report['total_items']} item berhasil dievaluasi.")
        elif status == "failed":
            st.error(f"❌ Run #{report['run_id']} gagal diproses.")

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        _render_metric_row(report["aggregate_live"], "📊 Agregat — Live Retrieval")
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        _render_metric_row(report["aggregate_reference"], "📌 Agregat — Reference Context (Terkunci)")

        by_cat = report.get("aggregate_by_category") or {}
        if by_cat:
            with st.expander("📂 Breakdown per Kategori", expanded=False):
                for cat, agg in by_cat.items():
                    _render_metric_row(agg, f"Kategori: {cat}")
                    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

        with st.expander("📋 Detail per Item", expanded=False):
            st.dataframe(
                [
                    {
                        "Item ID": it["dataset_item_id"],
                        "Pertanyaan": (it["question"][:60] + "…") if len(it["question"]) > 60 else it["question"],
                        "Tipe Eval": it["evaluation_type"],
                        "category": it.get("category") or "-",
                        "Faithfulness (QA)": it.get("faithfulness_qa"),
                        "Faithfulness (Summary)": it.get("faithfulness_summary"),
                        "Faithfulness (Risk)": it.get("risk_faithfulness"),
                        "Answer Relevancy": it.get("answer_relevancy"),
                        "Context Precision": it.get("context_precision"),
                        "Context Recall": it.get("context_recall"),
                    }
                    for it in report["items"]
                ],
                use_container_width=True,
                hide_index=True,
            )

    if auto_refresh and status not in ("completed", "failed"):
        st.caption("🔁 Auto-refresh aktif — memperbarui dalam 5 detik...")
        time.sleep(5)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────
# MAIN RENDER
# ─────────────────────────────────────────────────────────────────────────

def render_dataset_evaluation_tab():
    st.markdown(
        '<div class="ac-header">📁 Evaluasi Dataset (Golden Dataset)</div>'
        '<div class="ac-subheader">Kelola kumpulan soal kurasi, jalankan evaluasi batch, '
        'dan bandingkan skor RAGAS retrieval live vs referensi terkunci.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)

    tab_kelola, tab_csv, tab_run = st.tabs([
        "  📂  Kelola Dataset  ",
        "  📤  Upload Soal (CSV)  ",
        "  ▶️  Jalankan & Hasil  ",
    ])

    with tab_kelola:
        _subtab_kelola()
    with tab_csv:
        _subtab_upload_csv()
    with tab_run:
        _subtab_run()