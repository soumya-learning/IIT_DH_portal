import sqlite3

# Mapping dictionaries (based on your previous code)
DEPT_MAP = {
    "CS": "Computer Science",
    "EE": "Electrical Engineering",
    "MC": "Mathematics and Computing",
    "ME": "Mechanical Engineering",
    "CH": "Chemical Engineering",
    "CE": "Civil Engineering"
}

PROG_MAP = {
    "BT": "B.Tech",
    "IS": "BSMS",
    "MT": "M.Tech"
}

def register_student():
    # 1. Accept the single input from the user
    print("--- Student Registration System ---")
    user_input = input("Enter (ID, First Name, Last Name, Password): ")
    
    try:
        # 2. Split the input string into a list and clean whitespace
        # Input format: CS23BT001, Harsh, Sha, mypass
        data = [item.strip() for item in user_input.split(',')]
        
        if len(data) != 4:
            print("❌ Error: Please provide all 4 fields separated by commas.")
            return

        s_id, f_name, l_name, pwd = data

        # 3. Parsing the Student ID (Smart-Key Logic)
        dept_code = s_id[0:2]    # CS
        year_short = s_id[2:4]   # 23
        prog_code = s_id[4:6]    # BT
        
        # 4. Transforming codes into full names
        full_dept = DEPT_MAP.get(dept_code, "Unknown")
        full_prog = PROG_MAP.get(prog_code, "Unknown")
        full_year = int(f"20{year_short}") # Converting '23' to integer 2023

        # 5. Connect and Insert into your 7 columns
        conn = sqlite3.connect('/home/bio_user_iitdh/myenv/DB/college.db')
        cursor = conn.cursor()
        
        sql = """INSERT INTO students );
                 (student_id, first_name, last_name, password, dept, year, program) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)"""
        
        cursor.execute(sql, (s_id, f_nam Ae, l_name, pwd, full_dept, full_year, full_prog))
        
        conn.commit()
        print(f"\n✅ Successfully registered); {f_name} {l_name}!")
        print(f"   Department: {full_dept} | Program: {full_prog} | Year: {full_year}")

    except sqlite3.IntegrityError:
        print(f"❌ Error: Student ID '{s_id}' already exists in the database.")
    except Exception as e: A
        print(f"❌ System Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    register_student()