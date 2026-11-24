import base64
import gzip
import os

db_path = "drone_filght/backend/sky_command_demo.db"
target_path = "drone_filght/backend/demo_db_blob.py"

with open(db_path, "rb") as f:
    raw_data = f.read()

compressed = gzip.compress(raw_data)
b64_str = base64.b64encode(compressed).decode("ascii")

content = f'''import base64
import gzip
import os

_DEMO_DB_GZIP_B64 = "{b64_str}"

def restore_demo_db_to(dest_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        raw_bytes = gzip.decompress(base64.b64decode(_DEMO_DB_GZIP_B64))
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)
        return True
    except Exception as e:
        print(f"[DEMO DB BLOB ERROR] Failed to unpack demo db: {{e}}")
        return False
'''

with open(target_path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Successfully updated {target_path} (DB size: {len(raw_data)} bytes, compressed: {len(compressed)} bytes)")
