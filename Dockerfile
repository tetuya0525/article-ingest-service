# ==============================================================================
# Dockerfile for Article Ingest Service (v2 Final Corrected)
# ==============================================================================
# Use an official lightweight Python image.
FROM python:3.12-slim

# Set environment variables to prevent Python from buffering stdout and stderr.
ENV PYTHONUNBUFFERED True
# Set the working directory in the container.
ENV APP_HOME /app
WORKDIR $APP_HOME

# 1. Copy dependencies file first to leverage Docker cache.
COPY requirements.txt .

# 2. Install dependencies as root.
RUN pip install --no-cache-dir -r requirements.txt

# 3. Create a non-root user for security.
RUN adduser --system --group appuser

# 4. Copy the application code and change ownership.
COPY --chown=appuser:appuser . .

# 5. Switch to the non-root user.
USER appuser

# --- Corrected Gunicorn command ---
# Use 'exec' to ensure Gunicorn runs as PID 1 and receives signals correctly.
# Bind to the port specified by the Cloud Run $PORT environment variable.
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 "main:app"
