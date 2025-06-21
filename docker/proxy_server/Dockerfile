# Use Python 3.10 as required by the project
FROM tiangolo/uvicorn-gunicorn-fastapi:python3.10

# Set working directory
WORKDIR /app

COPY docker/proxy_server/main.py .

# Install dependencies
RUN pip install aiohttp Brotli

# Set environment variables
ENV PYTHONPATH=/app

# Expose port 9000
EXPOSE 8000

# Override the default CMD from the base image to directly run our app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
