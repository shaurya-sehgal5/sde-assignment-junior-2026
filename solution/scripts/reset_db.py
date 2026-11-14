from app.db.database import Base, engine

# Register all models before dropping tables.
from app.models import (
    Tenant,
    Campaign,
    Lead,
    CallAttempt,
    WebhookEvent,
    PhoneLock,
    PhoneSuppression,
)


def main():
    print("Resetting application database...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Database reset successfully.")


if __name__ == "__main__":
    main()
