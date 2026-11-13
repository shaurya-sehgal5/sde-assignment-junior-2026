from app.db.database import Base, engine, check_database

# Register all models
from app.models import (
    Tenant,
    Campaign,
    Lead,
    CallAttempt,
    WebhookEvent,
    PhoneLock,
    PhoneSuppression,
)


def initialize():
    print("Checking PostgreSQL connection...")

    result = check_database()
    print(f"Database connection successful: {result}")

    print("Creating database tables...")

    Base.metadata.create_all(bind=engine)

    print("Tables created successfully.")


if __name__ == "__main__":
    initialize()