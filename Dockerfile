FROM python:3.11-slim

# Install Chromium and required fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Set Chrome path for Zendriver
ENV CHROME_PATH=/usr/bin/chromium

# Set up a new user named "user" with user ID 1000
# (Strict requirement for Hugging Face Spaces)
RUN useradd -m -u 1000 user

# Switch to the "user" user
USER user

# Set home to the user's home directory
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set the working directory to the user's home directory
WORKDIR $HOME/app

# Copy requirements file and install dependencies
# We use --chown=user to ensure the user owns the files
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY --chown=user . .

# Hugging Face Spaces requires the app to listen on port 7860
ENV PORT=7860
EXPOSE 7860

# Run the application
CMD ["python", "main.py"]
