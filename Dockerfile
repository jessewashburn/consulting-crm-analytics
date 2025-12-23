FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Run migrations on startup (optional, can be done separately)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
