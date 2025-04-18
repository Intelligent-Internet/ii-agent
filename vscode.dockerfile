FROM node:18

# Install code-server
RUN curl -fsSL https://code-server.dev/install.sh | sh

# Expose port
EXPOSE 8080

# Start code-server
CMD ["code-server", "--auth", "password", "--bind-addr", "0.0.0.0:8080"]
