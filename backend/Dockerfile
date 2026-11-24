#This is a Dockerfile for a Python FastAPI application. It tells Docker how to build your application image and how to run your FastAPI server inside a container.

FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
