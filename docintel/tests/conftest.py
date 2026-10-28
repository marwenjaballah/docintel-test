import os

# Set dummy environment variables for automated test execution
os.environ.setdefault("API_KEY", "test-secret-key-123")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_docintel.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
