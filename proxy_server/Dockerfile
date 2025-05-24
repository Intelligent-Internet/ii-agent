# Use Python 3.10 as required by the project
FROM tiangolo/uvicorn-gunicorn-fastapi:python3.10

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY proxy_server/main.py ./proxy_server/

# Install dependencies
RUN pip install aiohttp

# Set environment variables
ENV PYTHONPATH=/app

# Expose port 8000
EXPOSE 8000

# Override the default CMD from the base image to directly run our app
CMD ["uvicorn", "proxy_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
