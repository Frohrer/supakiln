from db_models import SessionLocal

def get_db():
    """Database dependency to provide database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 