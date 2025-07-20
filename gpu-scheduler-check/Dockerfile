FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user for security
RUN groupadd -r testuser && useradd -r -g testuser testuser

# Set working directory
WORKDIR /app

# Create /tmp directory and set permissions for health checks
RUN mkdir -p /tmp && chown testuser:testuser /tmp

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Change ownership to non-root user
RUN chown -R testuser:testuser /app

# Switch to non-root user
USER testuser

# Health check using the file created by the application
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD test -f /tmp/healthy || exit 1

# Run the test service
CMD ["python", "app.py"] 