import sqlite3, json

conn = sqlite3.connect('/home/bio_user_iitdh/new_env/DB/college.db')
cursor = conn.cursor()

def decode_template(raw):
    """Unwrap any encoding layer to get raw fingerprint bytes."""
    if raw is None:
        return None
    raw = bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode()

    # Try to decode as UTF-8 text
    try:
        text = raw.decode("utf-8")

        # Case 1: stored as JSON array text "[3,3,92,...]"
        if text.startswith("["):
            lst = json.loads(text)
            if isinstance(lst, list):
                print(f"    Fixing: JSON text → raw bytes ({len(lst)} bytes)")
                return bytes(lst)

        # Case 2: stored as hex of JSON text "5b332c..."
        if text.startswith("5b"):
            try:
                inner = bytes.fromhex(text).decode("utf-8")
                lst = json.loads(inner)
                if isinstance(lst, list):
                    print(f"    Fixing: hex-of-JSON → raw bytes ({len(lst)} bytes)")
                    return bytes(lst)
            except (ValueError, UnicodeDecodeError):
                pass

        # Case 3: stored as plain hex string "03035c11..."
        try:
            decoded = bytes.fromhex(text)
            print(f"    Fixing: hex string → raw bytes ({len(decoded)} bytes)")
            return decoded
        except ValueError:
            pass

    except UnicodeDecodeError:
        # Already raw binary — no fix needed
        print(f"    Already raw bytes — no fix needed")
        return raw

    return raw


print("=== Migrating Students ===")
cursor.execute("SELECT student_id, template FROM students")
for student_id, template in cursor.fetchall():
    print(f"\n  {student_id}:")
    fixed = decode_template(template)
    if fixed and fixed != bytes(template if isinstance(template, (bytes, bytearray)) else b''):
        cursor.execute(
            "UPDATE students SET template = ? WHERE student_id = ?",
            (sqlite3.Binary(fixed), student_id)
        )
        print(f"    ✓ Updated to {len(fixed)} raw bytes")

print("\n=== Migrating Profs ===")
cursor.execute("SELECT prof_id, template FROM profs")
for prof_id, template in cursor.fetchall():
    print(f"\n  {prof_id}:")
    fixed = decode_template(template)
    if fixed and fixed != bytes(template if isinstance(template, (bytes, bytearray)) else b''):
        cursor.execute(
            "UPDATE profs SET template = ? WHERE prof_id = ?",
            (sqlite3.Binary(fixed), prof_id)
        )
        print(f"    ✓ Updated to {len(fixed)} raw bytes")

conn.commit()

# WAL flush so DB Browser sees it
cursor.execute("PRAGMA wal_checkpoint(FULL)")
conn.commit()
conn.close()

print("\n✅ Migration complete — close and reopen DB Browser to verify")