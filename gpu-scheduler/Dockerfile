FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN groupadd -r scheduler && useradd -r -g scheduler scheduler

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY scheduler.py .

# Change ownership to non-root user
RUN chown -R scheduler:scheduler /app

# Switch to non-root user
USER scheduler

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import kubernetes; print('healthy')" || exit 1

# Expose port (not strictly needed for scheduler but good practice)
EXPOSE 8080

# Run the scheduler
CMD ["python", "scheduler.py"] 