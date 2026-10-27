FROM python:3.11-slim

WORKDIR /app

# create non-root user
RUN useradd -m -u 1000 appuser

# install dependencies with network timeout protection
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# copy application code
COPY --chown=appuser:appuser app /app/app

# prepare uploads directory
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app/uploads

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
