#!/usr/bin/env python3
"""
IITDH Biometric Attendance System - Administrative Console
Manual data entry using system keyboard (no hardware required)
WITH OLED DISPLAY SUPPORT AND FINGERPRINT REGISTRATION
"""

import sqlite3
import sys
import serial
import time
from datetime import datetime
from adafruit_fingerprint import Adafruit_Fingerprint
from luma.oled.device import ssd1306
from luma.core.interface.serial import spi
from luma.core.render import canvas

# --- Database Configuration ---
DB_PATH = '/home/bio_user_iitdh/new_env/DB/college.db'

# --- Mapping Dictionaries ---
DEPT_MAP = {
    "CS": "Computer Science",
    "EE": "Electrical Engineering",
    "MC": "Math & Computing",
    "ME": "Mechanical Engineering",
    "CH": "Chemical Engineering",
    "CE": "Civil Engineering"
}

PROG_MAP = {
    "BT": "B.Tech",
    "IS": "BSMS",
    "MT": "M.Tech"
}

# --- OLED Setup ---
try:
    oled_interface = spi(device=0, port=0, bus_speed_hz=1000000, gpio_DC=25, gpio_RST=27, gpio_CS=8)
    device = ssd1306(oled_interface)
    device.contrast(255)
    OLED_AVAILABLE = True
    print("✅ OLED Display initialized")
except Exception as e:
    print(f"⚠️  OLED Display not available: {e}")
    OLED_AVAILABLE = False

# --- Fingerprint Sensor Setup ---
try:
    uart = serial.Serial("/dev/ttyUSB0", baudrate=57600, timeout=1)
    finger = Adafruit_Fingerprint(uart)
    FINGERPRINT_AVAILABLE = True
    print("✅ Fingerprint sensor initialized")
except Exception as e:
    print(f"⚠️  Fingerprint sensor not available: {e}")
    FINGERPRINT_AVAILABLE = False

def display_oled(line1, line2="", line3="", invert_header=False):
    """Display message on OLED in compact form"""
    if not OLED_AVAILABLE:
        return
    
    try:
        with canvas(device) as draw:
            if invert_header:
                # Inverted header bar
                draw.rectangle([(0, 0), (127, 14)], fill="white", outline="white")
                draw.text((5, 2), line1[:18], fill="black")
                draw.line([(0, 15), (127, 15)], fill="white", width=1)
                
                # Regular text below
                draw.text((5, 22), line2[:21], fill="white")
                draw.text((5, 40), line3[:21], fill="white")
            else:
                # Standard display
                draw.rectangle(device.bounding_box, outline="white")
                draw.text((5, 10), line1[:21], fill="white")
                draw.text((5, 28), line2[:21], fill="white")
                draw.text((5, 46), line3[:21], fill="white")
    except Exception as e:
        pass  # Silently fail if OLED has issues

def scan_fingerprint():
    """
    Scan fingerprint with 4-scan merging
    Returns fingerprint template or None
    """
    if not FINGERPRINT_AVAILABLE:
        print("❌ Fingerprint sensor not available")
        display_oled("ERROR", "No sensor")
        return None
    
    try:
        print("\n--- Starting 4-Scan Fingerprint Registration ---")
        display_oled("FINGERPRINT", "4 scans needed")
        time.sleep(2)
        
        # Scan 1: Base Template
        scan1_successful = False
        retry_attempts = 0
        max_initial_retries = 5
        
        while not scan1_successful and retry_attempts < max_initial_retries:
            print(f"📌 SCAN 1/4: Place finger on sensor...")
            display_oled("SCAN 1 of 4", "Place finger")
            uart.reset_input_buffer()
            
            finger_placed = False
            timeout = time.time() + 10
            while time.time() < timeout and not finger_placed:
                if finger.get_image() == 0:
                    finger_placed = True
                time.sleep(0.1)
            
            if not finger_placed:
                retry_attempts += 1
                print(f"⏱️  Timeout (attempt {retry_attempts}/{max_initial_retries})")
                display_oled("TIMEOUT", f"Try {retry_attempts}/{max_initial_retries}")
                time.sleep(1)
                continue
            
            if finger.image_2_tz(1) != 0:
                retry_attempts += 1
                print(f"❌ Bad image quality (attempt {retry_attempts}/{max_initial_retries})")
                display_oled("Bad Image", f"Try {retry_attempts}/{max_initial_retries}")
                time.sleep(1.5)
                continue
            
            print("✅ Scan 1 captured successfully")
            display_oled("SCAN 1 of 4", "Success!")
            time.sleep(1)
            scan1_successful = True
        
        if not scan1_successful:
            print("❌ Failed to get initial scan after multiple attempts")
            display_oled("FAILED", "Too many tries")
            time.sleep(2)
            return None
        
        # Scans 2-4: Iterative Merging
        for scan_num in range(2, 5):
            retry_count = 0
            max_retries = 5
            scan_successful = False
            
            while not scan_successful and retry_count < max_retries:
                # Remove finger
                print(f"📌 SCAN {scan_num}/4: Remove finger...")
                display_oled(f"SCAN {scan_num} of 4", "Remove finger")
                time.sleep(1.5)
                
                removal_timeout = time.time() + 5
                while time.time() < removal_timeout:
                    if finger.get_image() != 0:
                        break
                    time.sleep(0.1)
                
                # Place finger again
                print(f"📌 SCAN {scan_num}/4: Place finger again...")
                display_oled(f"SCAN {scan_num} of 4", "Place finger")
                
                finger_placed = False
                placement_timeout = time.time() + 10
                while time.time() < placement_timeout and not finger_placed:
                    if finger.get_image() == 0:
                        finger_placed = True
                    time.sleep(0.1)
                
                if not finger_placed:
                    retry_count += 1
                    display_oled("TIMEOUT", f"Retry {retry_count}/{max_retries}")
                    time.sleep(1.5)
                    continue
                
                if finger.image_2_tz(2) != 0:
                    retry_count += 1
                    print(f"❌ Bad image (attempt {retry_count}/{max_retries})")
                    display_oled("Bad Image", f"Retry {retry_count}/{max_retries}")
                    time.sleep(1.5)
                    continue
                
                # Merge with base template
                display_oled(f"SCAN {scan_num} of 4", "Merging...")
                
                if finger.create_model() == 0:
                    print(f"✅ Scan {scan_num} merged successfully")
                    display_oled(f"SCAN {scan_num} of 4", "Success!")
                    time.sleep(1)
                    scan_successful = True
                else:
                    retry_count += 1
                    print(f"⚠️  No match (attempt {retry_count}/{max_retries})")
                    display_oled("No Match", f"Retry {retry_count}/{max_retries}")
                    time.sleep(1.5)
            
            if not scan_successful:
                print(f"❌ Failed scan {scan_num} after {max_retries} attempts")
                display_oled("FAILED", "Too many tries")
                time.sleep(2)
                return None
        
        # Download template
        print("💾 Downloading fingerprint template...")
        display_oled("SAVING...", "Downloading")
        template = finger.get_fpdata("char", 1)
        
        if not template:
            print("❌ Failed to download template")
            display_oled("ERROR", "Download failed")
            time.sleep(2)
            return None
        
        print("✅ Fingerprint template captured successfully!")
        display_oled("SUCCESS!", "FP captured")
        time.sleep(1)
        return template
        
    except Exception as e:
        print(f"❌ Fingerprint error: {e}")
        display_oled("ERROR", str(e)[:21])
        return None

def print_header(title):
    """Print formatted header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def print_section(title):
    """Print section divider"""
    print("\n" + "-"*70)
    print(f"  {title}")
    print("-"*70)

def get_input(prompt, required=True, validation=None):
    """Get input with validation"""
    while True:
        value = input(f"{prompt}: ").strip()
        
        if not value and not required:
            return None
        
        if not value and required:
            print("❌ This field is required. Please try again.")
            continue
        
        if validation:
            valid, message = validation(value)
            if not valid:
                print(f"❌ {message}")
                continue
        
        return value

def validate_dept_code(code):
    """Validate department code"""
    code = code.upper()
    if code in DEPT_MAP:
        return True, None
    return False, f"Invalid department code. Valid codes: {', '.join(DEPT_MAP.keys())}"

def validate_prog_code(code):
    """Validate program code"""
    code = code.upper()
    if code in PROG_MAP:
        return True, None
    return False, f"Invalid program code. Valid codes: {', '.join(PROG_MAP.keys())}"

def validate_year(year):
    """Validate year"""
    try:
        y = int(year)
        if 2000 <= y <= 2100:
            return True, None
        return False, "Year must be between 2000 and 2100"
    except:
        return False, "Year must be a valid number"

def validate_email(email):
    """Basic email validation"""
    if '@' in email and '.' in email:
        return True, None
    return False, "Invalid email format"

# ==================== PROFESSOR REGISTRATION ====================

def register_professor():
    """Register a new professor (without fingerprint)"""
    print_header("PROFESSOR REGISTRATION")
    display_oled("ADMIN CONSOLE", "Prof Registration", invert_header=True)
    
    print("\n📝 Enter professor details manually")
    print("   (Note: Fingerprint must be registered separately using hardware)")
    
    try:
        # Get professor details
        display_oled("INPUT", "Enter Prof ID")
        prof_id = get_input("Professor ID (e.g., PROF001)").upper()
        display_oled("PROF ID", prof_id)
        
        # Check for duplicate
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT prof_id FROM profs WHERE prof_id=?", (prof_id,))
        if cursor.fetchone():
            print(f"\n❌ Error: Professor ID '{prof_id}' already exists")
            display_oled("ERROR", f"{prof_id} exists")
            conn.close()
            return
        conn.close()
        
        display_oled("INPUT", "Enter Name")
        prof_name = get_input("Full Name (e.g., John Smith)").title()
        display_oled("NAME", prof_name[:21])
        
        # Select department
        print("\nAvailable Departments:")
        for code, name in DEPT_MAP.items():
            print(f"  {code} - {name}")
        
        display_oled("INPUT", "Enter Dept Code")
        dept_code = get_input("Department Code", validation=validate_dept_code).upper()
        display_oled("DEPT", DEPT_MAP[dept_code][:21])
        
        display_oled("INPUT", "Email (optional)")
        email = get_input("Email (optional)", required=False, validation=lambda x: validate_email(x) if x else (True, None))
        
        if email:
            display_oled("EMAIL", email[:21])
        
        # Display summary
        print_section("SUMMARY")
        print(f"Professor ID:  {prof_id}")
        print(f"Name:          {prof_name}")
        print(f"Department:    {DEPT_MAP[dept_code]} ({dept_code})")
        if email:
            print(f"Email:         {email}")
        
        display_oled("SUMMARY", prof_id, prof_name[:21])
        
        confirm = input("\n✅ Save this professor? (yes/no): ").lower()
        
        if confirm in ['yes', 'y']:
            # Register fingerprint
            print("\n🔐 Now registering fingerprint...")
            display_oled("FINGERPRINT", "Starting scan")
            time.sleep(1)
            
            template = scan_fingerprint()
            
            if not template:
                print("\n⚠️  Fingerprint registration failed")
                retry = input("Would you like to save without fingerprint? (yes/no): ").lower()
                
                if retry not in ['yes', 'y']:
                    print("❌ Registration cancelled")
                    display_oled("CANCELLED", "Not saved")
                    return
                else:
                    # Use placeholder template
                    template = b'\x00' * 512
                    print("⚠️  Using placeholder fingerprint")
            
            display_oled("SAVING...", "To database")
            
            # Save to database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO profs (prof_id, name, template, dept_code, email) 
                VALUES (?, ?, ?, ?, ?)
            """, (prof_id, prof_name, sqlite3.Binary(bytearray(template)), dept_code, email))
            
            conn.commit()
            conn.close()
            
            print("\n✅ Professor registered successfully!")
            if len(template) > 512:
                print("✅ Fingerprint registered successfully!")
            else:
                print("⚠️  Fingerprint NOT registered - using placeholder")
            display_oled("SUCCESS!", prof_id, "Prof registered")
        else:
            print("\n❌ Registration cancelled")
            display_oled("CANCELLED", "Not saved")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])

# ==================== STUDENT REGISTRATION ====================

def register_student():
    """Register a new student (without fingerprint)"""
    print_header("STUDENT REGISTRATION")
    display_oled("ADMIN CONSOLE", "Student Register", invert_header=True)
    
    print("\n📝 Enter student details manually")
    print("   (Note: Fingerprint must be registered separately using hardware)")
    
    try:
        # Get department
        print("\nAvailable Departments:")
        for code, name in DEPT_MAP.items():
            print(f"  {code} - {name}")
        
        display_oled("INPUT", "Enter Dept Code")
        dept_code = get_input("Department Code", validation=validate_dept_code).upper()
        dept_name = DEPT_MAP[dept_code]
        display_oled("DEPT", dept_name[:21])
        
        # Get program
        print("\nAvailable Programs:")
        for code, name in PROG_MAP.items():
            print(f"  {code} - {name}")
        
        display_oled("INPUT", "Enter Prog Code")
        prog_code = get_input("Program Code", validation=validate_prog_code).upper()
        prog_name = PROG_MAP[prog_code]
        display_oled("PROGRAM", prog_name[:21])
        
        # Get batch year
        display_oled("INPUT", "Enter Year")
        batch_year = get_input("Batch Year (e.g., 2023)", validation=validate_year)
        year_short = batch_year[2:4]
        display_oled("YEAR", batch_year)
        
        # Get last 3 digits
        display_oled("INPUT", "Last 3 digits")
        roll_suffix = get_input("Last 3 digits of Roll No (e.g., 037)")
        
        if len(roll_suffix) != 3 or not roll_suffix.isdigit():
            print("❌ Error: Roll suffix must be exactly 3 digits")
            display_oled("ERROR", "Need 3 digits")
            return
        
        # Generate Roll Number
        roll_no = f"{dept_code}{year_short}{prog_code}{roll_suffix}"
        
        print(f"\n✅ Generated Roll Number: {roll_no}")
        display_oled("ROLL NUMBER", roll_no)
        
        # Check for duplicate
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE student_id=?", (roll_no,))
        if cursor.fetchone():
            print(f"❌ Error: Student ID '{roll_no}' already exists")
            display_oled("ERROR", f"{roll_no} exists")
            conn.close()
            return
        conn.close()
        
        # Get student name
        display_oled("INPUT", "First Name")
        first_name = get_input("First Name").title()
        display_oled("NAME", first_name[:21])
        
        display_oled("INPUT", "Last Name")
        last_name = get_input("Last Name").title()
        display_oled("NAME", f"{first_name} {last_name}"[:21])
        
        # Get password
        display_oled("INPUT", "Password")
        password = get_input("Password (numeric)")
        
        display_oled("INPUT", "Email (optional)")
        email = get_input("Email (optional)", required=False, validation=lambda x: validate_email(x) if x else (True, None))
        
        # Display summary
        print_section("SUMMARY")
        print(f"Student ID:    {roll_no}")
        print(f"Name:          {first_name} {last_name}")
        print(f"Department:    {dept_name}")
        print(f"Program:       {prog_name}")
        print(f"Batch Year:    {batch_year}")
        print(f"Password:      {'*' * len(password)}")
        if email:
            print(f"Email:         {email}")
        
        display_oled("SUMMARY", roll_no, f"{first_name} {last_name}"[:21])
        
        confirm = input("\n✅ Save this student? (yes/no): ").lower()
        
        if confirm in ['yes', 'y']:
            # Register fingerprint
            print("\n🔐 Now registering fingerprint...")
            display_oled("FINGERPRINT", "Starting scan")
            time.sleep(1)
            
            template = scan_fingerprint()
            
            if not template:
                print("\n⚠️  Fingerprint registration failed")
                retry = input("Would you like to save without fingerprint? (yes/no): ").lower()
                
                if retry not in ['yes', 'y']:
                    print("❌ Registration cancelled")
                    display_oled("CANCELLED", "Not saved")
                    return
                else:
                    # Use placeholder template
                    template = b'\x00' * 512
                    print("⚠️  Using placeholder fingerprint")
            
            display_oled("SAVING...", "To database")
            
            # Save to database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO students (student_id, first_name, last_name, password, dept, year, program, template, email) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (roll_no, first_name, last_name, password, dept_name, int(batch_year), prog_name, 
                  sqlite3.Binary(bytearray(template)), email))
            
            conn.commit()
            conn.close()
            
            print("\n✅ Student registered successfully!")
            if len(template) > 512:
                print("✅ Fingerprint registered successfully!")
            else:
                print("⚠️  Fingerprint NOT registered - using placeholder")
            display_oled("SUCCESS!", roll_no, "Student saved")
        else:
            print("\n❌ Registration cancelled")
            display_oled("CANCELLED", "Not saved")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])

# ==================== COURSE MANAGEMENT ====================

def add_course():
    """Add a new course"""
    print_header("COURSE ADDITION")
    display_oled("ADMIN CONSOLE", "Add Course", invert_header=True)
    
    print("\n📚 Enter course details")
    
    try:
        # Get course code
        display_oled("INPUT", "Course Code")
        course_code = get_input("Course Code (e.g., CS101)").upper()
        display_oled("COURSE", course_code)
        
        # Check for duplicate
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT course_code FROM courses WHERE course_code=?", (course_code,))
        if cursor.fetchone():
            print(f"\n❌ Error: Course '{course_code}' already exists")
            display_oled("ERROR", f"{course_code} exists")
            conn.close()
            return
        
        display_oled("INPUT", "Course Name")
        course_name = get_input("Course Name (e.g., Introduction to Programming)").title()
        display_oled("NAME", course_name[:21])
        
        # List available professors
        cursor.execute("SELECT prof_id, name, dept_code FROM profs ORDER BY prof_id")
        profs = cursor.fetchall()
        
        if not profs:
            print("\n❌ Error: No professors registered in the system")
            print("   Please register professors first")
            display_oled("ERROR", "No professors")
            conn.close()
            return
        
        print("\nAvailable Professors:")
        for prof_id, name, dept in profs:
            dept_name = DEPT_MAP.get(dept, dept)
            print(f"  {prof_id} - {name} ({dept_name})")
        
        display_oled("INPUT", "Professor ID")
        prof_id = get_input("Professor ID (who will teach this course)")
        
        # Verify professor exists
        cursor.execute("SELECT name FROM profs WHERE prof_id=?", (prof_id,))
        prof = cursor.fetchone()
        
        if not prof:
            print(f"❌ Error: Professor '{prof_id}' not found")
            display_oled("ERROR", "Prof not found")
            conn.close()
            return
        
        display_oled("PROF", prof[0][:21])
        
        # Select department for course
        print("\nCourse Department:")
        for code, name in DEPT_MAP.items():
            print(f"  {code} - {name}")
        
        display_oled("INPUT", "Dept Code")
        dept_code = get_input("Department Code", validation=validate_dept_code).upper()
        display_oled("DEPT", DEPT_MAP[dept_code][:21])
        
        # Optional fields
        display_oled("INPUT", "Semester (opt)")
        semester = get_input("Semester (e.g., Fall 2024, Spring 2025)", required=False)
        
        year = get_input("Academic Year (e.g., 2024)", required=False)
        time_slot = get_input("Time Slot (e.g., Mon/Wed 10:00-11:30)", required=False)
        
        # Display summary
        print_section("SUMMARY")
        print(f"Course Code:   {course_code}")
        print(f"Course Name:   {course_name}")
        print(f"Professor:     {prof[0]} ({prof_id})")
        print(f"Department:    {DEPT_MAP[dept_code]}")
        if semester:
            print(f"Semester:      {semester}")
        if year:
            print(f"Year:          {year}")
        if time_slot:
            print(f"Time Slot:     {time_slot}")
        
        display_oled("SUMMARY", course_code, course_name[:21])
        
        confirm = input("\n✅ Save this course? (yes/no): ").lower()
        
        if confirm in ['yes', 'y']:
            display_oled("SAVING...", "Please wait")
            
            cursor.execute("""
                INSERT INTO courses (course_code, course_name, prof_id, dept_code, semester, year, time_slot) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (course_code, course_name, prof_id, dept_code, semester, year, time_slot))
            
            conn.commit()
            conn.close()
            
            print("\n✅ Course added successfully!")
            print(f"   Students can now be enrolled in {course_code}")
            display_oled("SUCCESS!", course_code, "Course added")
        else:
            print("\n❌ Course addition cancelled")
            display_oled("CANCELLED", "Not saved")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])

def enroll_student_in_course():
    """Enroll a student in a course"""
    print_header("STUDENT COURSE ENROLLMENT")
    display_oled("ADMIN CONSOLE", "Enroll Student", invert_header=True)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get student ID
        display_oled("INPUT", "Student ID")
        student_id = get_input("Student ID (e.g., EE23BT037)").upper()
        display_oled("STUDENT", student_id)
        
        # Verify student exists
        cursor.execute("SELECT first_name, last_name, dept FROM students WHERE student_id=?", (student_id,))
        student = cursor.fetchone()
        
        if not student:
            print(f"❌ Error: Student '{student_id}' not found")
            display_oled("ERROR", "Not found")
            conn.close()
            return
        
        student_name = f"{student[0]} {student[1]}"
        print(f"\n✅ Student Found: {student_name} ({student[2]})")
        display_oled("FOUND", student_name[:21])
        
        # List available courses
        cursor.execute("""
            SELECT c.course_code, c.course_name, p.name 
            FROM courses c
            JOIN profs p ON c.prof_id = p.prof_id
            ORDER BY c.course_code
        """)
        courses = cursor.fetchall()
        
        if not courses:
            print("\n❌ Error: No courses available in the system")
            display_oled("ERROR", "No courses")
            conn.close()
            return
        
        print("\nAvailable Courses:")
        for code, name, prof in courses:
            print(f"  {code} - {name} (Prof. {prof})")
        
        display_oled("INPUT", "Course Code")
        course_code = get_input("Course Code to enroll in").upper()
        
        # Verify course exists
        cursor.execute("SELECT course_name FROM courses WHERE course_code=?", (course_code,))
        course = cursor.fetchone()
        
        if not course:
            print(f"❌ Error: Course '{course_code}' not found")
            display_oled("ERROR", "Course not found")
            conn.close()
            return
        
        display_oled("COURSE", course_code, course[0][:21])
        
        # Check if already enrolled
        cursor.execute("""
            SELECT enrollment_id FROM course_enrollments 
            WHERE student_id=? AND course_code=?
        """, (student_id, course_code))
        
        if cursor.fetchone():
            print(f"\n❌ Error: {student_name} is already enrolled in {course_code}")
            display_oled("ERROR", "Already enrolled")
            conn.close()
            return
        
        # Display summary
        print_section("ENROLLMENT SUMMARY")
        print(f"Student:       {student_name} ({student_id})")
        print(f"Course:        {course[0]} ({course_code})")
        
        display_oled("ENROLLING", student_id, course_code)
        
        confirm = input("\n✅ Confirm enrollment? (yes/no): ").lower()
        
        if confirm in ['yes', 'y']:
            display_oled("SAVING...", "Please wait")
            
            cursor.execute("""
                INSERT INTO course_enrollments (student_id, course_code, status)
                VALUES (?, ?, 'active')
            """, (student_id, course_code))
            
            conn.commit()
            conn.close()
            
            print("\n✅ Student enrolled successfully!")
            display_oled("SUCCESS!", student_id, f"→ {course_code}")
        else:
            print("\n❌ Enrollment cancelled")
            display_oled("CANCELLED", "Not saved")
            conn.close()
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])

def delete_student():
    """Delete a student by roll number"""
    print_header("DELETE STUDENT")
    display_oled("ADMIN CONSOLE", "Delete Student", invert_header=True)
    
    print("\n⚠️  WARNING: This will permanently delete the student and all related data!")
    print("   - Student record")
    print("   - Course enrollments")
    print("   - Attendance records")
    
    try:
        # Get student ID
        display_oled("INPUT", "Enter Roll No")
        student_id = get_input("Student Roll Number (e.g., EE23BT037)").upper()
        display_oled("SEARCHING", student_id)
        
        # Check if student exists
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT first_name, last_name, dept, year, program 
            FROM students 
            WHERE student_id=?
        """, (student_id,))
        
        student = cursor.fetchone()
        
        if not student:
            print(f"\n❌ Error: Student '{student_id}' not found")
            display_oled("ERROR", "Not found", student_id)
            conn.close()
            time.sleep(2)
            return
        
        first_name, last_name, dept, year, program = student
        student_name = f"{first_name} {last_name}"
        
        # Get enrollment count
        cursor.execute("""
            SELECT COUNT(*) FROM course_enrollments 
            WHERE student_id=?
        """, (student_id,))
        enrollment_count = cursor.fetchone()[0]
        
        # Get attendance count
        cursor.execute("""
            SELECT COUNT(*) FROM attendance 
            WHERE student_id=?
        """, (student_id,))
        attendance_count = cursor.fetchone()[0]
        
        # Display student details
        print_section("STUDENT DETAILS")
        print(f"Roll Number:   {student_id}")
        print(f"Name:          {student_name}")
        print(f"Department:    {dept}")
        print(f"Program:       {program}")
        print(f"Batch Year:    {year}")
        print(f"Enrollments:   {enrollment_count} courses")
        print(f"Attendance:    {attendance_count} records")
        
        display_oled("FOUND", student_name[:21], student_id)
        time.sleep(2)
        
        # Confirm deletion
        print("\n⚠️  ARE YOU SURE?")
        display_oled("CONFIRM?", "Delete student?", "yes/no")
        confirm = input("Type 'DELETE' to confirm deletion: ").strip()
        
        if confirm == "DELETE":
            display_oled("DELETING...", "Please wait")
            
            # Delete student (cascade will handle enrollments and attendance due to foreign keys)
            cursor.execute("DELETE FROM students WHERE student_id=?", (student_id,))
            
            conn.commit()
            conn.close()
            
            print(f"\n✅ Student '{student_name}' ({student_id}) deleted successfully")
            print(f"   • Student record deleted")
            print(f"   • {enrollment_count} course enrollments removed")
            print(f"   • {attendance_count} attendance records removed")
            
            display_oled("DELETED!", student_id, "All data removed")
            time.sleep(3)
        else:
            print("\n❌ Deletion cancelled - student data preserved")
            display_oled("CANCELLED", "Not deleted")
            conn.close()
            time.sleep(2)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        display_oled("ERROR", str(e)[:21])
        time.sleep(2)

def view_all_data():
    """View all data in the system"""
    print_header("SYSTEM DATA OVERVIEW")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Professors
        cursor.execute("SELECT COUNT(*) FROM profs")
        prof_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT prof_id, name, dept_code FROM profs ORDER BY prof_id")
        profs = cursor.fetchall()
        
        print_section(f"PROFESSORS ({prof_count})")
        if profs:
            for prof_id, name, dept in profs:
                print(f"  {prof_id}: {name} - {DEPT_MAP.get(dept, dept)}")
        else:
            print("  No professors registered")
        
        # Students
        cursor.execute("SELECT COUNT(*) FROM students")
        student_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT student_id, first_name, last_name, dept FROM students ORDER BY student_id LIMIT 10")
        students = cursor.fetchall()
        
        print_section(f"STUDENTS ({student_count})")
        if students:
            for sid, fname, lname, dept in students:
                print(f"  {sid}: {fname} {lname} - {dept}")
            if student_count > 10:
                print(f"  ... and {student_count - 10} more students")
        else:
            print("  No students registered")
        
        # Courses
        cursor.execute("SELECT COUNT(*) FROM courses")
        course_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT c.course_code, c.course_name, p.name 
            FROM courses c
            JOIN profs p ON c.prof_id = p.prof_id
            ORDER BY c.course_code
        """)
        courses = cursor.fetchall()
        
        print_section(f"COURSES ({course_count})")
        if courses:
            for code, name, prof in courses:
                # Get enrollment count
                cursor.execute("""
                    SELECT COUNT(*) FROM course_enrollments 
                    WHERE course_code=? AND status='active'
                """, (code,))
                enrollment = cursor.fetchone()[0]
                print(f"  {code}: {name} - Prof. {prof} ({enrollment} students)")
        else:
            print("  No courses added")
        
        # Attendance summary
        cursor.execute("""
            SELECT COUNT(DISTINCT student_id) FROM attendance 
            WHERE date(session_date) = date('now', 'localtime')
        """)
        today_attendance = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM attendance")
        total_attendance = cursor.fetchone()[0]
        
        print_section(f"ATTENDANCE RECORDS")
        print(f"  Today's Attendance: {today_attendance} students")
        print(f"  Total Records:      {total_attendance}")
        
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

# ==================== MAIN MENU ====================

def main_menu():
    """Main menu for administrative tasks"""
    while True:
        print_header("IITDH BIOMETRIC ATTENDANCE - ADMIN CONSOLE")
        display_oled("ADMIN CONSOLE", "Ready", "Select option", invert_header=True)
        
        print("\n📋 Administrative Options:")
        print("  1. Register Professor (with Fingerprint)")
        print("  2. Register Student (with Fingerprint)")
        print("  3. Add Course")
        print("  4. Enroll Student in Course")
        print("  5. Delete Student")
        print("  6. View All System Data")
        print("  7. Exit")
        
        choice = input("\n👉 Select option (1-7): ").strip()
        
        if choice == '1':
            register_professor()
        elif choice == '2':
            register_student()
        elif choice == '3':
            add_course()
        elif choice == '4':
            enroll_student_in_course()
        elif choice == '5':
            delete_student()
        elif choice == '6':
            view_all_data()
        elif choice == '7':
            print("\n" + "="*70)
            print("  👋 Goodbye! Have a great day!")
            print("="*70 + "\n")
            display_oled("GOODBYE", "System exit")
            break
        else:
            print("\n❌ Invalid choice. Please select 1-7")
            display_oled("ERROR", "Invalid choice")
        
        input("\n⏎ Press Enter to continue...")

# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("  IITDH BIOMETRIC ATTENDANCE SYSTEM")
    print("  Administrative Console - Complete Registration")
    print("="*70)
    print("\n📝 FEATURES:")
    print("  • Manual data entry via system keyboard")
    print("  • Fingerprint registration (4-scan merging)")
    print("  • OLED display feedback")
    print("  • Complete student/professor management")
    print("  • Course management and enrollment")
    print("  • Student deletion with cascade")
    print("\n💾 Database: " + DB_PATH)
    
    if FINGERPRINT_AVAILABLE:
        print("✅ Fingerprint sensor: Available")
    else:
        print("⚠️  Fingerprint sensor: Not available (will use placeholders)")
    
    if OLED_AVAILABLE:
        print("✅ OLED display: Available")
        display_oled("IITDH ADMIN", "Initializing...", invert_header=True)
    else:
        print("⚠️  OLED display: Not available")
    
    try:
        # Verify database exists
        conn = sqlite3.connect(DB_PATH)
        conn.close()
        print("✅ Database connection: Successful\n")
        
        if OLED_AVAILABLE:
            display_oled("ADMIN CONSOLE", "DB Connected", "Ready", invert_header=True)
        
        input("⏎ Press Enter to start...")
        
        main_menu()
        
    except Exception as e:
        print(f"\n❌ Error connecting to database: {e}")
        print("\n💡 TIP: Run 'python3 setup_database.py' first to create the database")
        if OLED_AVAILABLE:
            display_oled("ERROR", "DB not found")
        sys.exit(1)