# Use Python 3.14 slim image as requested
FROM python:3.14-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create data directory for local SQLite fallback
RUN mkdir -p data

# Expose port 8000 (Mandatory for Semicolons deployment)
EXPOSE 8000

# Run the application
# Using --host 0.0.0.0 to allow external access within the container
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
