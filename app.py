import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date, timedelta
import math

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
SUPABASE_URL = "https://peagkvkhhsbdytevnhia.supabase.co"
SUPABASE_KEY = "sb_secret_Q0zxaI4Myb6lY0IWZKgjLw_pXGH5zXj"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="IITDH Attendance Portal", page_icon="🎓", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

.stApp, .main { background-color: #ffffff !important; font-family: 'Sora', sans-serif !important; }
.block-container { padding-top: 2.5rem !important; background-color: #ffffff !important; }
h1, h2, h3, h4, h5, h6 { color: #111111 !important; font-family: 'Sora', sans-serif !important; }
.stMarkdown p { color: #111111 !important; }

/* ── Nav buttons ──────────────────────────────────────────── */
.nav-btn button {
    width: 100% !important;
    border: none !important;
    border-bottom: 3px solid #e5e7eb !important;
    border-radius: 0 !important;
    background: #f9fafb !important;
    color: #444444 !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    padding: 0.65rem 0.2rem !important;
    font-family: 'Sora', sans-serif !important;
    white-space: nowrap !important;
}
.nav-btn button:hover {
    background: #f0f0f0 !important;
    color: #111111 !important;
}
.nav-btn-active button {
    width: 100% !important;
    border: none !important;
    border-bottom: 3px solid #111111 !important;
    border-radius: 0 !important;
    background: #ffffff !important;
    color: #111111 !important;
    font-size: 0.88rem !important;
    font-weight: 700 !important;
    padding: 0.65rem 0.2rem !important;
    font-family: 'Sora', sans-serif !important;
    white-space: nowrap !important;
}
/* ── Metrics ──────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #f9fafb; border: 1px solid #e5e7eb;
    border-radius: 10px; padding: 1rem !important;
}
[data-testid="stMetricLabel"] { color: #555555 !important; font-size: 0.82rem !important; }
[data-testid="stMetricValue"] { color: #111111 !important; font-size: 1.6rem !important; font-weight: 700 !important; }

/* ── Session card ─────────────────────────────────────────── */
.sess-card {
    background: #f9fafb; border: 1px solid #e5e7eb;
    border-left: 4px solid #111111; border-radius: 10px;
    padding: 1rem 1.2rem; margin-bottom: 0.75rem;
    transition: box-shadow 0.15s; font-family: 'Sora', sans-serif;
}
.sess-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.09); }
.sess-card-code { font-family:'JetBrains Mono',monospace; font-size:0.75rem;
                  font-weight:700; letter-spacing:0.1em; text-transform:uppercase;
                  color:#111111; margin-bottom:0.3rem; }
.sess-card-name { font-size:0.95rem; font-weight:600; color:#111111; margin-bottom:0.3rem; }
.sess-card-prof { font-size:0.8rem; color:#555555; }
.sess-card-meta { font-family:'JetBrains Mono',monospace; font-size:0.75rem;
                  color:#777777; margin-top:0.3rem; }

/* ── Hero banner ──────────────────────────────────────────── */
.hero-wrap {
    background: #f3f4f6; border: 1px solid #d1d5db;
    border-left: 6px solid #111111; border-radius: 12px;
    padding: 1.8rem 2.2rem; margin-bottom: 1.5rem;
    font-family: 'Sora', sans-serif;
}
.hero-title { font-size:1.9rem; font-weight:700; color:#111111; margin:0 0 0.3rem 0; }
.hero-sub   { font-size:0.88rem; color:#555555; margin:0; }
.hero-date  { font-family:'JetBrains Mono',monospace; font-size:0.82rem; color:#111111; margin-top:0.5rem; }

/* ── Section headers ──────────────────────────────────────── */
.sec-header {
    font-family: 'Sora', sans-serif; font-size: 1rem; font-weight: 700;
    color: #111111; border-bottom: 2px solid #111111;
    padding-bottom: 0.4rem; margin: 1.4rem 0 0.9rem 0;
    text-transform: uppercase; letter-spacing: 0.06em;
}

/* ── Expander ─────────────────────────────────────────────── */
[data-testid="stExpander"] { border: 1px solid #e5e7eb !important; border-radius: 8px !important; margin-bottom: 0.5rem !important; }
[data-testid="stExpander"] summary > span { font-family: 'JetBrains Mono', monospace !important; font-size: 0.83rem !important; color: #111111 !important; font-weight: 600 !important; }

/* ── Status bar ───────────────────────────────────────────── */
.status-bar {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #111111; color: #ffffff; text-align: center;
    padding: 5px 0; font-size: 11px; font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.06em; z-index: 9999; border-top: 1px solid #333;
}

/* ── Click hint ───────────────────────────────────────────── */
.click-hint {
    font-size: 0.8rem; color: #777777; margin-bottom: 0.4rem;
    padding: 6px 10px; background: #f9fafb;
    border-left: 3px solid #d1d5db; border-radius: 4px;
}
</style>
<div class="status-bar">IITDH ATTENDANCE PORTAL &nbsp;·&nbsp; SYSTEM ONLINE &nbsp;·&nbsp; IIT DHARWAD</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def fetch_table(table_name):
    try:
        r = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(r.data)
    except Exception as e:
        st.error(f"Error fetching {table_name}: {e}")
        return pd.DataFrame()

def detect_date_col(df):
    for c in ["date","class_date","attendance_date","timestamp","created_at"]:
        if c in df.columns: return c
    return None

def detect_stu_id_col(df):
    for c in ["student_id","roll_no","roll","id"]:
        if c in df.columns: return c
    return None

def activity_ring_html(attended, total, student_label=""):
    pct   = round((attended / total) * 100, 1) if total > 0 else 0
    color = "#16a34a" if pct >= 75 else ("#ca8a04" if pct >= 50 else "#dc2626")
    badge = "Eligible" if pct >= 75 else ("At Risk" if pct >= 50 else "Below Threshold")
    R, cx, cy, sw = 60, 80, 80, 14
    circ = 2 * math.pi * R
    dash = circ * pct / 100
    gap  = circ - dash
    return f"""
    <div style="display:flex;flex-direction:column;align-items:center;gap:10px;padding:12px 0;font-family:'Sora',sans-serif;">
      <div style="font-size:0.8rem;color:#555;font-weight:500;text-align:center;">{student_label}</div>
      <svg viewBox="0 0 160 160" width="190" height="190" xmlns="http://www.w3.org/2000/svg">
        <circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="#e5e7eb" stroke-width="{sw}"/>
        <circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{color}" stroke-width="{sw}"
                stroke-linecap="round" stroke-dasharray="{dash:.2f} {gap:.2f}"
                transform="rotate(-90 {cx} {cy})">
          <animate attributeName="stroke-dasharray" from="0 {circ:.2f}" to="{dash:.2f} {gap:.2f}" dur="0.8s" fill="freeze"/>
        </circle>
        <text x="{cx}" y="{cy-7}" text-anchor="middle" dominant-baseline="middle"
              font-family="'JetBrains Mono',monospace" font-size="24" font-weight="700" fill="{color}">{pct}%</text>
        <text x="{cx}" y="{cy+16}" text-anchor="middle" dominant-baseline="middle"
              font-family="'Sora',sans-serif" font-size="10" fill="#777777">{attended} / {total} classes</text>
      </svg>
      <div style="display:flex;gap:16px;font-size:11px;color:#555;">
        <span style="display:flex;align-items:center;gap:5px;">
          <span style="width:10px;height:10px;border-radius:50%;background:{color};display:inline-block;"></span>Attended
        </span>
        <span style="display:flex;align-items:center;gap:5px;">
          <span style="width:10px;height:10px;border-radius:50%;background:#e5e7eb;border:1px solid #d1d5db;display:inline-block;"></span>Absent
        </span>
      </div>
      <div style="background:#f3f4f6;color:{color};border:1.5px solid #e5e7eb;border-radius:999px;padding:5px 18px;font-size:13px;font-weight:600;">{badge}</div>
    </div>"""


# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
attendance_df = fetch_table("attendance")
students_df   = fetch_table("students")
courses_df    = fetch_table("courses")
profs_df      = fetch_table("profs")

date_col     = detect_date_col(attendance_df)
stu_id_col_a = detect_stu_id_col(attendance_df)
stu_id_col_s = detect_stu_id_col(students_df)

if not attendance_df.empty and date_col:
    attendance_df[date_col] = pd.to_datetime(attendance_df[date_col], errors="coerce")

def build_course_lookup():
    lookup = {}
    if courses_df.empty: return lookup
    name_c = next((c for c in ["course_name","name","title"] if c in courses_df.columns), None)
    prof_c = next((c for c in ["prof_name","professor_name","instructor","faculty"] if c in courses_df.columns), None)
    prof_map = {}
    if not profs_df.empty:
        pid = next((c for c in ["prof_id","id"] if c in profs_df.columns), None)
        pnm = next((c for c in ["prof_name","name","full_name"] if c in profs_df.columns), None)
        if pid and pnm:
            for _, r in profs_df.iterrows():
                prof_map[str(r[pid])] = str(r[pnm])
    for _, row in courses_df.iterrows():
        code  = str(row.get("course_code",""))
        cname = str(row.get(name_c, code)) if name_c else code
        pval  = str(row.get(prof_c, ""))   if prof_c else ""
        lookup[code] = {"name": cname, "prof": prof_map.get(pval, pval)}
    return lookup

course_lookup = build_course_lookup()


# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION  — full-width columns + buttons (guaranteed single line)
# ─────────────────────────────────────────────────────────────────────────────
NAV_LABELS = ["Home", "Attendance", "Students", "Professors", "Courses", "Att. Log"]

if "page" not in st.session_state:
    st.session_state.page = "Home"

cols = st.columns(len(NAV_LABELS))
for i, label in enumerate(NAV_LABELS):
    css_class = "nav-btn-active" if st.session_state.page == label else "nav-btn"
    with cols[i]:
        st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
        if st.button(label, key=f"nav_{label}", use_container_width=True):
            st.session_state.page = label
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

page = st.session_state.page
st.markdown("<hr style='margin:0 0 1.2rem 0; border-color:#e5e7eb;'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════════════════════════
if page == "Home":
    today     = date.today()
    today_str = today.strftime("%A, %d %B %Y")

    st.markdown(f"""
    <div class="hero-wrap">
      <div class="hero-title">IITDH Attendance Portal</div>
      <div class="hero-sub">Indian Institute of Technology Dharwad — Academic Attendance System</div>
      <div class="hero-date">{today_str}</div>
    </div>""", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Students",     len(students_df)   if not students_df.empty   else 0)
    c2.metric("Courses",      len(courses_df)    if not courses_df.empty    else 0)
    c3.metric("Faculty",      len(profs_df)      if not profs_df.empty      else 0)
    c4.metric("Total Swipes", len(attendance_df) if not attendance_df.empty else 0)

    st.markdown('<div class="sec-header">Sessions Today</div>', unsafe_allow_html=True)
    if attendance_df.empty or not date_col:
        st.info("No attendance data available.")
    else:
        today_att = attendance_df[attendance_df[date_col].dt.date == today]
        if today_att.empty:
            st.info("No sessions recorded for today yet.")
        else:
            grouped = list(today_att.groupby("course_code"))
            cols = st.columns(min(3, len(grouped)))
            for i, (code, grp) in enumerate(grouped):
                info = course_lookup.get(code, {"name": code, "prof": "—"})
                with cols[i % len(cols)]:
                    st.markdown(f"""
                    <div class="sess-card">
                      <div class="sess-card-code">{code}</div>
                      <div class="sess-card-name">{info['name']}</div>
                      <div class="sess-card-prof">Prof: {info['prof'] or '—'}</div>
                      <div class="sess-card-meta">{len(grp)} swipe(s) recorded</div>
                    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="sec-header">Recent Sessions — Last 7 Days</div>', unsafe_allow_html=True)
    if not attendance_df.empty and date_col:
        week_ago = pd.Timestamp(today) - timedelta(days=7)
        recent   = attendance_df[attendance_df[date_col] >= week_ago].copy()
        recent["_date"] = recent[date_col].dt.date
        if recent.empty:
            st.info("No sessions in the last 7 days.")
        else:
            sessions = (recent.groupby(["_date","course_code"])
                        .size().reset_index(name="swipes")
                        .sort_values("_date", ascending=False))
            cols = st.columns(3)
            for i, row in sessions.iterrows():
                info = course_lookup.get(row["course_code"], {"name": row["course_code"], "prof": "—"})
                with cols[i % 3]:
                    st.markdown(f"""
                    <div class="sess-card">
                      <div class="sess-card-code">{row['course_code']}</div>
                      <div class="sess-card-name">{info['name']}</div>
                      <div class="sess-card-prof">Prof: {info['prof'] or '—'}</div>
                      <div class="sess-card-meta">{row['_date'].strftime('%d %b %Y')} · {row['swipes']} swipe(s)</div>
                    </div>""", unsafe_allow_html=True)
    else:
        st.info("No attendance data available.")


# ══════════════════════════════════════════════════════════════════════════════
# ATTENDANCE LOGS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Attendance":
    st.header("Attendance Records")
    if attendance_df.empty:
        st.info("No attendance records found.")
    else:
        all_courses = sorted(attendance_df["course_code"].dropna().unique().tolist())
        sel_courses = st.multiselect("Filter by Course", options=all_courses, default=all_courses)
        filt = attendance_df[attendance_df["course_code"].isin(sel_courses)]
        st.metric("Total Swipes Shown", len(filt))

        if date_col:
            filt = filt.copy()
            filt["_date"] = filt[date_col].dt.date
            grouped     = filt.groupby(["_date","course_code"])
            sorted_keys = sorted(grouped.groups.keys(), reverse=True)
            for (sess_date, code) in sorted_keys:
                grp  = grouped.get_group((sess_date, code))
                info = course_lookup.get(code, {"name": code, "prof": "—"})
                with st.expander(
                    f"{code} — {info['name']}  |  "
                    f"{sess_date.strftime('%d %b %Y')}  |  "
                    f"Prof: {info['prof'] or '—'}  |  "
                    f"{len(grp)} swipe(s)"
                ):
                    st.dataframe(grp.drop(columns=["_date"], errors="ignore").reset_index(drop=True), use_container_width=True)
        else:
            for code in sel_courses:
                grp  = filt[filt["course_code"] == code]
                info = course_lookup.get(code, {"name": code, "prof": "—"})
                with st.expander(f"{code} — {info['name']}  |  {len(grp)} swipe(s)"):
                    st.dataframe(grp.reset_index(drop=True), use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT DIRECTORY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Students":
    st.header("Registered Students")
    df = students_df.copy()
    if not df.empty:
        search = st.text_input("Search by Name or ID")
        if search:
            df = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No students enrolled yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PROFESSOR LIST
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Professors":
    st.header("Faculty Members")
    if not profs_df.empty:
        cols_to_show = [c for c in profs_df.columns if c != "template"]
        st.table(profs_df[cols_to_show])
    else:
        st.info("No professor records found.")


# ══════════════════════════════════════════════════════════════════════════════
# COURSE CATALOG
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Courses":
    st.header("Course Catalog")
    df = courses_df.copy()
    if not df.empty:
        col_type, col_query = st.columns([1, 3])
        with col_type:
            search_type = st.selectbox("Search by", ["Course Code", "Course Name", "Professor Name"])
        with col_query:
            search_query = st.text_input("Search term", placeholder=f"Type {search_type.lower()}...")
        if search_query:
            col_map = {
                "Course Code":    ["course_code","code"],
                "Course Name":    ["course_name","name","title"],
                "Professor Name": ["prof_name","professor_name","instructor","faculty"],
            }
            mc = next((c for c in col_map[search_type] if c in df.columns), None)
            if mc:
                df = df[df[mc].astype(str).str.contains(search_query, case=False, na=False)]
            else:
                st.warning(f"Column for '{search_type}' not found. Available: {list(df.columns)}")
        st.write(f"Showing **{len(df)}** course(s):")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No courses created in database.")


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT ATTENDANCE LOG
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Att. Log":
    st.header("Student Attendance Log")
    st.markdown('<div class="click-hint">Click any row in the table to see that student\'s attendance ring</div>', unsafe_allow_html=True)

    if courses_df.empty or attendance_df.empty or students_df.empty:
        st.info("Requires data in courses, attendance, and students tables.")
    else:
        name_col_c = next((c for c in ["course_name","name","title"] if c in courses_df.columns), None)
        id_col     = stu_id_col_s or (students_df.columns[0] if not students_df.empty else "id")
        name_col_s = next((c for c in ["name","student_name","full_name"] if c in students_df.columns), None)

        for _, course_row in courses_df.iterrows():
            code        = str(course_row.get("course_code",""))
            course_name = str(course_row.get(name_col_c, code)) if name_col_c else code
            course_att  = attendance_df[attendance_df["course_code"] == code].copy()

            if date_col:
                total_classes = course_att[date_col].dt.date.nunique()
            else:
                total_classes = len(course_att)

            if stu_id_col_a and stu_id_col_s:
                if date_col:
                    course_att["_date"] = course_att[date_col].dt.date
                    per_stu = (course_att.groupby(stu_id_col_a)["_date"]
                               .nunique().reset_index(name="Classes Attended"))
                else:
                    per_stu = (course_att.groupby(stu_id_col_a)
                               .size().reset_index(name="Classes Attended"))

                merged = students_df.merge(
                    per_stu.rename(columns={stu_id_col_a: stu_id_col_s}),
                    on=stu_id_col_s, how="left"
                )
                merged["Classes Attended"] = merged["Classes Attended"].fillna(0).astype(int)
                display_df = merged[list(students_df.columns) + ["Classes Attended"]].reset_index(drop=True)
            else:
                display_df = students_df.copy().reset_index(drop=True)

            with st.expander(f"{code}  —  {course_name}   |   Total Classes Held: {total_classes}", expanded=False):
                if display_df.empty:
                    st.info("No students enrolled.")
                    continue

                event = st.dataframe(
                    display_df,
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"sel_{code}",
                )

                selected_rows = event.selection.rows if event and hasattr(event, "selection") else []

                if selected_rows:
                    stu_row  = display_df.iloc[selected_rows[0]]
                    attended = int(stu_row.get("Classes Attended", 0))
                    pct      = round((attended / total_classes) * 100, 1) if total_classes > 0 else 0
                    stu_id   = stu_row.get(id_col, "—")
                    stu_name = stu_row.get(name_col_s, "") if name_col_s else ""
                    label    = f"{stu_id}  ·  {stu_name}" if stu_name else str(stu_id)

                    st.markdown("---")
                    ring_col, info_col = st.columns([1, 1])
                    with ring_col:
                        st.markdown(activity_ring_html(attended, total_classes, label), unsafe_allow_html=True)
                    with info_col:
                        st.markdown(f"**Student ID:** `{stu_id}`")
                        if name_col_s:
                            st.markdown(f"**Name:** {stu_name}")
                        for col in ["year","department","program","dept","branch"]:
                            if col in stu_row.index and pd.notna(stu_row[col]):
                                st.markdown(f"**{col.capitalize()}:** {stu_row[col]}")
                        st.markdown(f"**Attended:** {attended} / {total_classes} classes")
                        if pct >= 75:
                            st.success(f"**{pct}%** — Eligible")
                        elif pct >= 50:
                            st.warning(f"**{pct}%** — At Risk")
                        else:
                            st.error(f"**{pct}%** — Below Threshold")
