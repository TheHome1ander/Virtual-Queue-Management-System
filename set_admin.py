from database import SessionLocal, engine, Base
from models import User

# Ensure tables exist
Base.metadata.create_all(bind=engine)

db = SessionLocal()

print("--- STARTING ADMIN SETUP ---")

# 1. Search for existing admin
existing_admin = db.query(User).filter(User.username == "admin").first()

if existing_admin:
    print(f"Updating existing admin (ID: {existing_admin.id})...")
    existing_admin.password = "adminpassword"
    existing_admin.role = "admin"
else:
    print("Creating NEW admin...")
    new_admin = User(username="admin", password="adminpassword", role="admin")
    db.add(new_admin)

try:
    db.commit()
    print("SUCCESS: Admin 'admin' with password 'adminpassword' is ready.")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    db.close()