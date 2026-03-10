FROM python:3.11-slim

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy project files
COPY backend/ backend/
COPY frontend/ frontend/

EXPOSE 8000

CMD ["python", "backend/main.py"]
