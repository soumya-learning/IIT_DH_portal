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


/* ── Edit panel ───────────────────────────────────────────── */
.edit-panel {
    background: #fafafa; border: 1.5px solid #d1d5db;
    border-left: 5px solid #111111; border-radius: 10px;
    padding: 1.4rem 1.6rem; margin: 1rem 0;
    font-family: 'Sora', sans-serif;
}
.edit-panel-title {
    font-size: 0.9rem; font-weight: 700; color: #111111;
    text-transform: uppercase; letter-spacing: 0.07em;
    margin-bottom: 1rem; display: flex; align-items: center; gap: 8px;
}
.danger-zone {
    background: #fff5f5; border: 1.5px solid #fecaca;
    border-left: 5px solid #dc2626; border-radius: 10px;
    padding: 1.4rem 1.6rem; margin: 1rem 0;
}
</style>
<div class="status-bar">IITDH ATTENDANCE PORTAL &nbsp;·&nbsp; SYSTEM ONLINE &nbsp;·&nbsp; IIT DHARWAD</div>
""", unsafe_allow_html=True)




# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


HIDDEN_COLS = {"template", "created_at", "password_hash", "password"}




def clean(df):
    drop = [c for c in df.columns if c in HIDDEN_COLS]
    return df.drop(columns=drop, errors="ignore")




@st.cache_data(ttl=60)
def fetch_table(table_name):
    try:
        r = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(r.data)
    except Exception as e:
        st.error(f"Error fetching {table_name}: {e}")
        return pd.DataFrame()




def refresh_all():
    fetch_table.clear()
    st.rerun()




def detect_date_col(df):
    for c in ["date", "class_date", "attendance_date", "timestamp", "created_at", "session_date"]:
        if c in df.columns:
            return c
    return None




def detect_stu_id_col(df):
    for c in ["student_id", "roll_no", "roll", "id"]:
        if c in df.columns:
            return c
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
attendance_df    = fetch_table("attendance")
students_df      = fetch_table("students")
courses_df       = fetch_table("courses")
profs_df         = fetch_table("profs")
enrollments_df   = fetch_table("course_enrollments")


date_col     = detect_date_col(attendance_df)
stu_id_col_a = detect_stu_id_col(attendance_df)
stu_id_col_s = detect_stu_id_col(students_df)


# Use session_date if present, else timestamp for attendance
if not attendance_df.empty:
    if "session_date" in attendance_df.columns:
        date_col = "session_date"
    elif "timestamp" in attendance_df.columns:
        date_col = "timestamp"


if not attendance_df.empty and date_col:
    attendance_df[date_col] = pd.to_datetime(attendance_df[date_col], errors="coerce")




def build_course_lookup():
    lookup = {}
    if courses_df.empty:
        return lookup
    name_c = next((c for c in ["course_name", "name", "title"] if c in courses_df.columns), None)
    prof_map = {}
    if not profs_df.empty:
        pid = next((c for c in ["prof_id", "id"] if c in profs_df.columns), None)
        pnm = next((c for c in ["prof_name", "name", "full_name"] if c in profs_df.columns), None)
        if pid and pnm:
            for _, r in profs_df.iterrows():
                prof_map[str(r[pid])] = str(r[pnm])
    for _, row in courses_df.iterrows():
        code  = str(row.get("course_code", ""))
        cname = str(row.get(name_c, code)) if name_c else code
        # courses table links via prof_id -> profs table
        prof_id_val = str(row.get("prof_id", ""))
        resolved_prof = prof_map.get(prof_id_val, prof_id_val)
        lookup[code] = {"name": cname, "prof": resolved_prof, "prof_id": prof_id_val}
    return lookup




course_lookup = build_course_lookup()




# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────
NAV_LABELS = ["Home", "Attendance", "Students", "Professors", "Courses", "Att. Log", "⚙ Manage"]


if "page" not in st.session_state:
    st.session_state.page = "Home"


nav_cols = st.columns(len(NAV_LABELS))
for i, label in enumerate(NAV_LABELS):
    css_class = "nav-btn-active" if st.session_state.page == label else "nav-btn"
    with nav_cols[i]:
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
            sessions = (recent.groupby(["_date", "course_code"])
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
            grouped     = filt.groupby(["_date", "course_code"])
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
                    st.dataframe(clean(grp.drop(columns=["_date"], errors="ignore").reset_index(drop=True)), use_container_width=True)
        else:
            for code in sel_courses:
                grp  = filt[filt["course_code"] == code]
                info = course_lookup.get(code, {"name": code, "prof": "—"})
                with st.expander(f"{code} — {info['name']}  |  {len(grp)} swipe(s)"):
                    st.dataframe(clean(grp.reset_index(drop=True)), use_container_width=True)




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
        st.dataframe(clean(df), use_container_width=True)
    else:
        st.info("No students enrolled yet.")




# ══════════════════════════════════════════════════════════════════════════════
# PROFESSOR LIST
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Professors":
    st.header("Faculty Members")
    if not profs_df.empty:
        st.table(clean(profs_df))
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
                "Course Code":    ["course_code", "code"],
                "Course Name":    ["course_name", "name", "title"],
                "Professor Name": ["prof_name", "professor_name", "instructor", "faculty"],
            }
            mc = next((c for c in col_map[search_type] if c in df.columns), None)
            if mc:
                df = df[df[mc].astype(str).str.contains(search_query, case=False, na=False)]
            else:
                st.warning(f"Column for '{search_type}' not found. Available: {list(df.columns)}")
        st.write(f"Showing **{len(df)}** course(s):")
        st.dataframe(clean(df), use_container_width=True)
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
        name_col_c = next((c for c in ["course_name", "name", "title"] if c in courses_df.columns), None)
        id_col     = stu_id_col_s or (students_df.columns[0] if not students_df.empty else "id")
        name_col_s = next((c for c in ["name", "student_name", "full_name", "first_name"] if c in students_df.columns), None)


        # ── Search Bar ────────────────────────────────────────────────────────
        st.markdown('<div class="sec-header">Search</div>', unsafe_allow_html=True)
        search_col1, search_col2 = st.columns([1, 3])
        with search_col1:
            search_type = st.selectbox(
                "Search by",
                ["Course Code", "Course Name", "Professor Name", "Student Name", "Student ID"],
                key="att_log_search_type"
            )
        with search_col2:
            search_query = st.text_input(
                "Search term",
                placeholder=f"Type {search_type.lower()}...",
                key="att_log_search_query"
            )


        filtered_courses = courses_df.copy()


        if search_query:
            q = search_query.strip().lower()
            if search_type == "Course Code":
                filtered_courses = filtered_courses[
                    filtered_courses["course_code"].astype(str).str.lower().str.contains(q, na=False)
                ]
            elif search_type == "Course Name":
                if name_col_c:
                    filtered_courses = filtered_courses[
                        filtered_courses[name_col_c].astype(str).str.lower().str.contains(q, na=False)
                    ]
                else:
                    filtered_courses = filtered_courses.iloc[0:0]
            elif search_type == "Professor Name":
                def get_prof_name(code):
                    return course_lookup.get(str(code), {}).get("prof", "").lower()
                mask = filtered_courses["course_code"].apply(get_prof_name).str.contains(q, na=False)
                filtered_courses = filtered_courses[mask]
            elif search_type in ("Student Name", "Student ID"):
                stu_search_df = students_df.copy()
                if search_type == "Student Name" and name_col_s:
                    stu_search_df = stu_search_df[
                        stu_search_df[name_col_s].astype(str).str.lower().str.contains(q, na=False)
                    ]
                elif search_type == "Student ID" and stu_id_col_s:
                    stu_search_df = stu_search_df[
                        stu_search_df[stu_id_col_s].astype(str).str.lower().str.contains(q, na=False)
                    ]
                matching_ids = stu_search_df[stu_id_col_s].tolist() if stu_id_col_s else []
                if matching_ids and stu_id_col_a:
                    relevant_codes = attendance_df[
                        attendance_df[stu_id_col_a].isin(matching_ids)
                    ]["course_code"].unique().tolist()
                    filtered_courses = filtered_courses[filtered_courses["course_code"].isin(relevant_codes)]
                else:
                    filtered_courses = filtered_courses.iloc[0:0]


        if filtered_courses.empty:
            st.info("No courses match your search." if search_query else "No courses found.")
        else:
            st.markdown(
                f"<p style='color:#555;font-size:0.85rem;margin-bottom:0.5rem;'>Showing <strong>{len(filtered_courses)}</strong> course(s)</p>",
                unsafe_allow_html=True
            )


        for _, course_row in filtered_courses.iterrows():
            code        = str(course_row.get("course_code", ""))
            course_name = str(course_row.get(name_col_c, code)) if name_col_c else code
            info        = course_lookup.get(code, {"name": course_name, "prof": "—"})
            prof_name   = info.get("prof", "—") or "—"
            course_att  = attendance_df[attendance_df["course_code"] == code].copy()


            if date_col:
                total_classes = course_att[date_col].dt.date.nunique()
            else:
                total_classes = len(course_att)


            if not enrollments_df.empty and "course_code" in enrollments_df.columns and "student_id" in enrollments_df.columns:
                enrolled_ids = enrollments_df[
                    (enrollments_df["course_code"] == code) &
                    (enrollments_df.get("status", pd.Series(["active"] * len(enrollments_df))).isin(["active", "Active"]) if "status" in enrollments_df.columns else True)
                ]["student_id"].tolist()
                enrolled_students_df = students_df[students_df[stu_id_col_s].isin(enrolled_ids)].copy() if stu_id_col_s else students_df.copy()
            else:
                enrolled_ids = course_att[stu_id_col_a].unique().tolist() if stu_id_col_a and not course_att.empty else []
                enrolled_students_df = students_df[students_df[stu_id_col_s].isin(enrolled_ids)].copy() if stu_id_col_s and enrolled_ids else students_df.copy()


            total_enrolled = len(enrolled_students_df)


            if stu_id_col_a and stu_id_col_s:
                if date_col:
                    course_att["_date"] = course_att[date_col].dt.date
                    per_stu = (course_att.groupby(stu_id_col_a)["_date"]
                               .nunique().reset_index(name="Classes Attended"))
                else:
                    per_stu = (course_att.groupby(stu_id_col_a)
                               .size().reset_index(name="Classes Attended"))


                merged = enrolled_students_df.merge(
                    per_stu.rename(columns={stu_id_col_a: stu_id_col_s}),
                    on=stu_id_col_s, how="left"
                )
                merged["Classes Attended"] = merged["Classes Attended"].fillna(0).astype(int)


                if search_query and search_type in ("Student Name", "Student ID"):
                    q = search_query.strip().lower()
                    if search_type == "Student Name" and name_col_s:
                        merged = merged[
                            merged[name_col_s].astype(str).str.lower().str.contains(q, na=False)
                        ]
                    elif search_type == "Student ID" and stu_id_col_s:
                        merged = merged[
                            merged[stu_id_col_s].astype(str).str.lower().str.contains(q, na=False)
                        ]


                orig_cols  = [c for c in students_df.columns if c not in HIDDEN_COLS]
                display_df = merged[orig_cols + ["Classes Attended"]].reset_index(drop=True)
            else:
                display_df = clean(enrolled_students_df.copy()).reset_index(drop=True)


            expander_label = (
                f"{code}  —  {course_name}"
                f"   |   Prof: {prof_name}"
                f"   |   Classes Held: {total_classes}"
                f"   |   Enrolled Students: {total_enrolled}"
            )
            with st.expander(expander_label, expanded=bool(search_query)):
                ci1, ci2, ci3, ci4 = st.columns(4)
                ci1.markdown(f"**Course Code:** `{code}`")
                ci2.markdown(f"**Professor:** {prof_name}")
                ci3.markdown(f"**Classes Held:** {total_classes}")
                ci4.markdown(f"**Enrolled Students:** {total_enrolled}")
                extra_course_cols = [
                    c for c in courses_df.columns
                    if c not in HIDDEN_COLS
                    and c not in {"course_code", "course_name", "name", "title",
                                  "prof_name", "professor_name", "instructor", "faculty", "prof_id"}
                ]
                if extra_course_cols:
                    extra_vals = {c: course_row.get(c, "") for c in extra_course_cols if pd.notna(course_row.get(c, ""))}
                    if extra_vals:
                        ex_cols = st.columns(min(4, len(extra_vals)))
                        for i, (k, v) in enumerate(extra_vals.items()):
                            ex_cols[i % len(ex_cols)].markdown(f"**{k.replace('_',' ').title()}:** {v}")
                st.markdown("---")
                if display_df.empty:
                    st.info("No students match your search for this course." if search_query else "No students enrolled.")
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
                        skip_cols = {id_col, name_col_s, "Classes Attended"} | HIDDEN_COLS
                        for col in stu_row.index:
                            if col not in skip_cols and pd.notna(stu_row[col]) and str(stu_row[col]).strip():
                                st.markdown(f"**{col.replace('_',' ').title()}:** {stu_row[col]}")
                        st.markdown(f"**Attended:** {attended} / {total_classes} classes")
                        if pct >= 75:
                            st.success(f"**{pct}%** — Eligible")
                        elif pct >= 50:
                            st.warning(f"**{pct}%** — At Risk")
                        else:
                            st.error(f"**{pct}%** — Below Threshold")




# ══════════════════════════════════════════════════════════════════════════════
# MANAGE — Edit / Admin Panel
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙ Manage":
    st.header("⚙ Manage — Admin Operations")
    st.markdown(
        "<p style='color:#555;font-size:0.88rem;margin-bottom:1.5rem;'>"
        "Use this panel to add courses, enrol students, remove enrolments, or delete students from the registry."
        "</p>",
        unsafe_allow_html=True
    )


    tab1, tab2, tab3, tab4 = st.tabs([
        "➕  Add Course",
        "📋  Enrol Student",
        "🗑  Remove Enrolment",
        "❌  Delete Student",
    ])


    # ──────────────────────────────────────────────────────────────────────────
    # TAB 1 — ADD COURSE
    # ──────────────────────────────────────────────────────────────────────────
    with tab1:
        st.markdown('<div class="sec-header">Add New Course</div>', unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#555;font-size:0.85rem;margin-bottom:1rem;'>"
            "Fill in the details below. Course Code must be unique.</p>",
            unsafe_allow_html=True
        )


        with st.form("add_course_form", clear_on_submit=True):
            fc1, fc2 = st.columns(2)
            with fc1:
                new_code = st.text_input(
                    "Course Code *",
                    placeholder="e.g. CS301",
                    help="Unique identifier like CS301, EE202"
                )
                new_name = st.text_input(
                    "Course Name *",
                    placeholder="e.g. Data Structures & Algorithms"
                )
            with fc2:
                # Build prof options from profs table
                prof_options = {}
                if not profs_df.empty:
                    pid_col = next((c for c in ["prof_id", "id"] if c in profs_df.columns), None)
                    pnm_col = next((c for c in ["name", "prof_name", "full_name"] if c in profs_df.columns), None)
                    if pid_col and pnm_col:
                        for _, pr in profs_df.iterrows():
                            prof_options[f"{pr[pnm_col]} ({pr[pid_col]})"] = str(pr[pid_col])


                if prof_options:
                    selected_prof_label = st.selectbox(
                        "Professor *",
                        options=list(prof_options.keys()),
                        help="Select the professor who will teach this course"
                    )
                    selected_prof_id = prof_options[selected_prof_label]
                else:
                    st.warning("No professors found in the database. Please add professors first.")
                    selected_prof_id = st.text_input("Professor ID (manual)", placeholder="e.g. PROF001")
                    selected_prof_label = selected_prof_id


                # Optional fields
                dept_options = ["CS", "EE", "MC", "ME", "CH", "CE", ""]
                new_dept = st.selectbox("Department (optional)", options=dept_options, index=len(dept_options)-1)
                new_semester = st.text_input("Semester (optional)", placeholder="e.g. 2024-ODD")
                new_year = st.number_input("Year (optional)", min_value=2020, max_value=2035, value=date.today().year, step=1)
                new_timeslot = st.text_input("Time Slot (optional)", placeholder="e.g. Mon/Wed 10:00–11:00")


            submitted = st.form_submit_button("➕ Add Course", use_container_width=True, type="primary")


        if submitted:
            # Validate required fields
            errors = []
            if not new_code.strip():
                errors.append("Course Code is required.")
            if not new_name.strip():
                errors.append("Course Name is required.")
            if not selected_prof_id or not selected_prof_id.strip():
                errors.append("Professor is required.")


            # Check duplicate course code
            if not courses_df.empty and new_code.strip() in courses_df["course_code"].astype(str).values:
                errors.append(f"Course Code **{new_code.strip()}** already exists.")


            if errors:
                for e in errors:
                    st.error(e)
            else:
                payload = {
                    "course_code": new_code.strip().upper(),
                    "course_name": new_name.strip(),
                    "prof_id":     selected_prof_id.strip(),
                }
                if new_dept:
                    payload["dept_code"] = new_dept
                if new_semester.strip():
                    payload["semester"] = new_semester.strip()
                if new_year:
                    payload["year"] = int(new_year)
                if new_timeslot.strip():
                    payload["time_slot"] = new_timeslot.strip()
                try:
                    result = supabase.table("courses").insert(payload).execute()
                    if result.data:
                        st.success(
                            f"✅ Course **{new_code.strip().upper()} — {new_name.strip()}** "
                            f"added successfully with Prof. {selected_prof_label}!"
                        )
                        fetch_table.clear()
                    else:
                        st.error("Insert failed. No data returned from Supabase.")
                except Exception as ex:
                    st.error(f"Error adding course: {ex}")


        # Show current courses
        st.markdown('<div class="sec-header">Existing Courses</div>', unsafe_allow_html=True)
        if not courses_df.empty:
            display_courses = clean(courses_df.copy())
            # Resolve prof_id to name for display
            if not profs_df.empty:
                pid_col = next((c for c in ["prof_id", "id"] if c in profs_df.columns), None)
                pnm_col = next((c for c in ["name", "prof_name", "full_name"] if c in profs_df.columns), None)
                if pid_col and pnm_col and "prof_id" in display_courses.columns:
                    prof_id_to_name = dict(zip(profs_df[pid_col].astype(str), profs_df[pnm_col].astype(str)))
                    display_courses["professor"] = display_courses["prof_id"].astype(str).map(prof_id_to_name).fillna(display_courses["prof_id"])
            st.dataframe(display_courses, use_container_width=True)
        else:
            st.info("No courses in database yet.")


    # ──────────────────────────────────────────────────────────────────────────
    # TAB 2 — ENROL STUDENT IN COURSE
    # ──────────────────────────────────────────────────────────────────────────
    with tab2:
        st.markdown('<div class="sec-header">Enrol Student in Course</div>', unsafe_allow_html=True)


        if students_df.empty:
            st.warning("No students found in the database.")
        elif courses_df.empty:
            st.warning("No courses found in the database.")
        else:
            # Build student options
            stu_options = {}
            name_col_s2 = next((c for c in ["first_name", "name", "student_name", "full_name"] if c in students_df.columns), None)
            last_col    = next((c for c in ["last_name"] if c in students_df.columns), None)
            sid_col     = stu_id_col_s or students_df.columns[0]


            for _, sr in students_df.iterrows():
                sid  = str(sr[sid_col])
                if name_col_s2 and last_col:
                    sname = f"{sr[name_col_s2]} {sr[last_col]}"
                elif name_col_s2:
                    sname = str(sr[name_col_s2])
                else:
                    sname = sid
                stu_options[f"{sname} ({sid})"] = sid


            # Build course options
            crs_options = {}
            name_col_c2 = next((c for c in ["course_name", "name", "title"] if c in courses_df.columns), None)
            for _, cr in courses_df.iterrows():
                ccode = str(cr["course_code"])
                cname = str(cr[name_col_c2]) if name_col_c2 else ccode
                crs_options[f"{ccode} — {cname}"] = ccode


            with st.form("enrol_student_form", clear_on_submit=True):
                enrol_stu_label = st.selectbox("Select Student *", options=list(stu_options.keys()))
                enrol_crs_label = st.selectbox("Select Course *",  options=list(crs_options.keys()))
                enrol_submitted = st.form_submit_button("📋 Enrol Student", use_container_width=True, type="primary")


            if enrol_submitted:
                enrol_stu_id  = stu_options[enrol_stu_label]
                enrol_crs_code = crs_options[enrol_crs_label]


                # Check if already enrolled
                already = False
                if not enrollments_df.empty and "student_id" in enrollments_df.columns and "course_code" in enrollments_df.columns:
                    already = (
                        (enrollments_df["student_id"].astype(str) == enrol_stu_id) &
                        (enrollments_df["course_code"].astype(str) == enrol_crs_code)
                    ).any()


                if already:
                    st.warning(f"⚠ **{enrol_stu_label}** is already enrolled in **{enrol_crs_label}**.")
                else:
                    try:
                        result = supabase.table("course_enrollments").insert({
                            "student_id":  enrol_stu_id,
                            "course_code": enrol_crs_code,
                            "status":      "active"
                        }).execute()
                        if result.data:
                            st.success(f"✅ **{enrol_stu_label}** successfully enrolled in **{enrol_crs_label}**!")
                            fetch_table.clear()
                        else:
                            st.error("Enrolment failed. No data returned.")
                    except Exception as ex:
                        st.error(f"Error enrolling student: {ex}")


            # Show current enrollments
            st.markdown('<div class="sec-header">Current Enrolments</div>', unsafe_allow_html=True)
            if not enrollments_df.empty:
                enrol_display = enrollments_df.copy()
                # Merge student names
                if not students_df.empty and sid_col in students_df.columns:
                    if name_col_s2 and last_col:
                        students_df["_display_name"] = students_df[name_col_s2].astype(str) + " " + students_df[last_col].astype(str)
                    elif name_col_s2:
                        students_df["_display_name"] = students_df[name_col_s2].astype(str)
                    else:
                        students_df["_display_name"] = students_df[sid_col].astype(str)
                    name_map = dict(zip(students_df[sid_col].astype(str), students_df["_display_name"]))
                    enrol_display["student_name"] = enrol_display["student_id"].astype(str).map(name_map)
                # Merge course names
                if not courses_df.empty and name_col_c2:
                    cname_map = dict(zip(courses_df["course_code"].astype(str), courses_df[name_col_c2].astype(str)))
                    enrol_display["course_name"] = enrol_display["course_code"].astype(str).map(cname_map)
                show_cols = [c for c in ["enrollment_id", "student_id", "student_name", "course_code", "course_name", "status", "enrolled_date"]
                             if c in enrol_display.columns]
                st.dataframe(enrol_display[show_cols], use_container_width=True)
            else:
                st.info("No enrolment records found.")


    # ──────────────────────────────────────────────────────────────────────────
    # TAB 3 — REMOVE STUDENT FROM COURSE
    # ──────────────────────────────────────────────────────────────────────────
    with tab3:
        st.markdown('<div class="sec-header">Remove Student from Course</div>', unsafe_allow_html=True)


        if enrollments_df.empty:
            st.info("No enrolment records found.")
        else:
            # Build searchable enrollment list
            enrol_display3 = enrollments_df.copy()
            sid_col3    = stu_id_col_s or students_df.columns[0] if not students_df.empty else "student_id"
            name_col_s3 = next((c for c in ["first_name", "name", "student_name"] if c in students_df.columns), None)
            last_col3   = next((c for c in ["last_name"] if c in students_df.columns), None)
            name_col_c3 = next((c for c in ["course_name", "name", "title"] if c in courses_df.columns), None)


            if not students_df.empty:
                if name_col_s3 and last_col3:
                    students_df["_dn3"] = students_df[name_col_s3].astype(str) + " " + students_df[last_col3].astype(str)
                elif name_col_s3:
                    students_df["_dn3"] = students_df[name_col_s3].astype(str)
                else:
                    students_df["_dn3"] = students_df[sid_col3].astype(str)
                nm3 = dict(zip(students_df[sid_col3].astype(str), students_df["_dn3"]))
                enrol_display3["student_name"] = enrol_display3["student_id"].astype(str).map(nm3).fillna(enrol_display3["student_id"])


            if not courses_df.empty and name_col_c3:
                cn3 = dict(zip(courses_df["course_code"].astype(str), courses_df[name_col_c3].astype(str)))
                enrol_display3["course_name"] = enrol_display3["course_code"].astype(str).map(cn3).fillna(enrol_display3["course_code"])


            # Search within enrollments
            rem_search = st.text_input("🔍 Filter by student name, student ID, or course code", key="rem_search")
            filtered_enrol = enrol_display3.copy()
            if rem_search:
                q3 = rem_search.lower()
                filtered_enrol = filtered_enrol[
                    filtered_enrol.astype(str).apply(lambda x: x.str.lower().str.contains(q3)).any(axis=1)
                ]


            show_cols3 = [c for c in ["enrollment_id", "student_id", "student_name", "course_code", "course_name", "status"]
                          if c in filtered_enrol.columns]


            st.markdown(
                f"<p style='color:#555;font-size:0.85rem;margin-bottom:0.4rem;'>"
                f"Showing <strong>{len(filtered_enrol)}</strong> enrolment(s). Select a row to remove.</p>",
                unsafe_allow_html=True
            )


            rem_event = st.dataframe(
                filtered_enrol[show_cols3].reset_index(drop=True),
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key="rem_enrol_table"
            )


            rem_selected = rem_event.selection.rows if rem_event and hasattr(rem_event, "selection") else []


            if rem_selected:
                sel_enrol_row = filtered_enrol[show_cols3].reset_index(drop=True).iloc[rem_selected[0]]
                eid      = sel_enrol_row.get("enrollment_id", None)
                rem_sid  = sel_enrol_row.get("student_id", "—")
                rem_sname= sel_enrol_row.get("student_name", rem_sid)
                rem_ccode= sel_enrol_row.get("course_code", "—")
                rem_cname= sel_enrol_row.get("course_name", rem_ccode)


                st.markdown(f"""
                <div class="edit-panel">
                  <div class="edit-panel-title">🗑 Remove Enrolment</div>
                  <p style='color:#333;font-size:0.9rem;'>
                    You are about to remove <strong>{rem_sname}</strong> ({rem_sid})
                    from <strong>{rem_ccode} — {rem_cname}</strong>.
                  </p>
                  <p style='color:#555;font-size:0.82rem;'>
                    This only removes the course enrolment. The student's attendance history
                    for this course will remain in the attendance log. The student will NOT
                    be deleted from the registry.
                  </p>
                </div>
                """, unsafe_allow_html=True)


                confirm_col1, confirm_col2 = st.columns([1, 3])
                with confirm_col1:
                    if st.button(
                        f"🗑 Remove from {rem_ccode}",
                        key="confirm_remove_enrolment",
                        type="primary",
                        use_container_width=True
                    ):
                        try:
                            if eid is not None:
                                supabase.table("course_enrollments").delete().eq("enrollment_id", int(eid)).execute()
                            else:
                                supabase.table("course_enrollments").delete()\
                                    .eq("student_id", rem_sid)\
                                    .eq("course_code", rem_ccode)\
                                    .execute()
                            st.success(
                                f"✅ **{rem_sname}** has been removed from **{rem_ccode} — {rem_cname}**."
                            )
                            fetch_table.clear()
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Error removing enrolment: {ex}")


    # ──────────────────────────────────────────────────────────────────────────
    # TAB 4 — DELETE STUDENT FROM REGISTRY (double confirmation)
    # ──────────────────────────────────────────────────────────────────────────
    with tab4:
        st.markdown('<div class="sec-header">Delete Student from Registry</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="danger-zone">
          <p style='color:#991b1b;font-size:0.9rem;font-weight:700;margin:0 0 0.5rem 0;'>
            ⚠ DANGER ZONE — Irreversible Action
          </p>
          <p style='color:#7f1d1d;font-size:0.84rem;margin:0;'>
            Deleting a student will permanently remove them from the student registry,
            all course enrolments, and all attendance records. This action cannot be undone.
            You will be asked to confirm <strong>twice</strong>.
          </p>
        </div>
        """, unsafe_allow_html=True)


        if students_df.empty:
            st.info("No students found in the database.")
        else:
            # Step 1: Search and select student
            del_search = st.text_input("🔍 Search student by name or ID", key="del_search")
            del_df = students_df.copy()
            if del_search:
                del_df = del_df[
                    del_df.astype(str).apply(lambda x: x.str.lower().str.contains(del_search.lower())).any(axis=1)
                ]


            sid_col4    = stu_id_col_s or students_df.columns[0]
            name_col_s4 = next((c for c in ["first_name", "name", "student_name"] if c in students_df.columns), None)
            last_col4   = next((c for c in ["last_name"] if c in students_df.columns), None)


            del_display = clean(del_df.copy()).reset_index(drop=True)
            st.markdown(
                f"<p style='color:#555;font-size:0.85rem;margin-bottom:0.4rem;'>"
                f"Showing <strong>{len(del_display)}</strong> student(s). Select a row to delete.</p>",
                unsafe_allow_html=True
            )


            del_event = st.dataframe(
                del_display,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key="del_stu_table"
            )


            del_selected = del_event.selection.rows if del_event and hasattr(del_event, "selection") else []


            if del_selected:
                del_row   = del_display.iloc[del_selected[0]]
                del_sid   = str(del_row.get(sid_col4, "—"))
                if name_col_s4 and last_col4:
                    del_name = f"{del_row.get(name_col_s4, '')} {del_row.get(last_col4, '')}".strip()
                elif name_col_s4:
                    del_name = str(del_row.get(name_col_s4, del_sid))
                else:
                    del_name = del_sid


                # Count courses enrolled and attendance records
                enrolled_count = 0
                att_count      = 0
                if not enrollments_df.empty and "student_id" in enrollments_df.columns:
                    enrolled_count = len(enrollments_df[enrollments_df["student_id"].astype(str) == del_sid])
                if not attendance_df.empty and stu_id_col_a and stu_id_col_a in attendance_df.columns:
                    att_count = len(attendance_df[attendance_df[stu_id_col_a].astype(str) == del_sid])


                st.markdown(f"""
                <div class="danger-zone">
                  <p style='color:#991b1b;font-size:0.92rem;font-weight:700;margin:0 0 0.6rem 0;'>
                    Selected Student for Deletion
                  </p>
                  <p style='color:#333;font-size:0.9rem;margin:0 0 0.3rem 0;'>
                    <strong>Name:</strong> {del_name} &nbsp;|&nbsp;
                    <strong>ID:</strong> <code>{del_sid}</code>
                  </p>
                  <p style='color:#7f1d1d;font-size:0.83rem;margin:0;'>
                    This will delete: <strong>{enrolled_count}</strong> course enrolment(s)
                    and <strong>{att_count}</strong> attendance record(s).
                  </p>
                </div>
                """, unsafe_allow_html=True)


                # ── CONFIRMATION 1 ────────────────────────────────────────────
                st.markdown("**Confirmation 1 of 2**")
                confirm1 = st.checkbox(
                    f"I understand that **{del_name} ({del_sid})** will be permanently removed from all courses and the registry.",
                    key="del_confirm1"
                )


                if confirm1:
                    # ── CONFIRMATION 2 ────────────────────────────────────────
                    st.markdown("**Confirmation 2 of 2**")
                    type_confirm = st.text_input(
                        f'Type the Student ID **{del_sid}** below to confirm deletion:',
                        key="del_confirm2_input",
                        placeholder=f"Type {del_sid} here"
                    )
                    confirm2_match = type_confirm.strip() == del_sid


                    if type_confirm and not confirm2_match:
                        st.warning("Student ID does not match. Please type it exactly.")


                    del_btn_disabled = not (confirm1 and confirm2_match)
                    if st.button(
                        f"❌ Permanently Delete {del_name}",
                        key="final_delete_btn",
                        type="primary",
                        disabled=del_btn_disabled,
                        use_container_width=True
                    ):
                        try:
                            # Delete from attendance (if no cascade)
                            try:
                                supabase.table("attendance").delete().eq("student_id", del_sid).execute()
                            except Exception:
                                pass  # cascade may handle it


                            # Delete from course_enrollments (if no cascade)
                            try:
                                supabase.table("course_enrollments").delete().eq("student_id", del_sid).execute()
                            except Exception:
                                pass  # cascade may handle it


                            # Delete the student record
                            supabase.table("students").delete().eq(sid_col4, del_sid).execute()


                            st.success(
                                f"✅ Student **{del_name} ({del_sid})** has been permanently deleted "
                                f"from the registry, all course enrolments, and all attendance records."
                            )
                            fetch_table.clear()
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Error deleting student: {ex}")



