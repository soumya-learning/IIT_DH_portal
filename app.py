import streamlit as st
from supabase import create_client
import pandas as pd

# --- CONFIGURATION ---
# Replace with your actual Supabase credentials
SUPABASE_URL = "https://peagkvkhhsbdytevnhia.supabase.co"
SUPABASE_KEY = "sb_secret_Q0zxaI4Myb6lY0IWZKgjLw_pXGH5zXj" # Use Service Role for the dashboard

# Initialize Supabase Client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- PAGE SETUP ---
st.set_page_config(page_title="IITDH Attendance-Portal", page_icon="🎓", layout="wide")

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Attendance Logs", "Student Directory", "Professor List", "Course Catalog"])

# --- HELPER FUNCTION TO FETCH DATA ---
def fetch_table(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error fetching {table_name}: {e}")
        return pd.DataFrame()

# --- LOGIC FOR EACH PAGE ---

if page == "Attendance Logs":
    st.title("📊 Attendance Records")
    df = fetch_table("attendance")
    
    if not df.empty:
        # Filters
        courses = df['course_code'].unique()
        selected_course = st.sidebar.multiselect("Filter by Course", options=courses, default=courses)
        
        filtered_df = df[df['course_code'].isin(selected_course)]
        
        st.metric("Total Swipes", len(filtered_df))
        st.dataframe(filtered_df, use_container_width=True)
    else:
        st.info("No attendance records found.")

elif page == "Student Directory":
    st.title("👨‍🎓 Registered Students")
    df = fetch_table("students")
    
    if not df.empty:
        # Search functionality
        search = st.text_input("Search by Name or ID")
        if search:
            df = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
        
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No students enrolled yet.")

elif page == "Professor List":
    st.title("👨‍🏫 Faculty Members")
    df = fetch_table("profs")
    
    if not df.empty:
        st.table(df) # Static table looks cleaner for small lists
    else:
        st.info("No professor records found.")

elif page == "Course Catalog":
    st.title("📚 Available Courses")
    df = fetch_table("courses")
    
    if not df.empty:
        st.write("Current courses offered at IITDH:")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No courses created in database.")

# --- FOOTER ---
st.sidebar.markdown("---")
st.sidebar.write("🟢 System Status: Online")