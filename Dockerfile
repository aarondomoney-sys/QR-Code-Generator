FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENV DATA_DIR=/data
EXPOSE 8080
CMD ["python3", "app.py"]
