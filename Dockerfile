FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src
ENV LEARNING_APP_DATA_DIR=/app/data
ENV LEARNING_APP_CONTENT_DIR=/app/content/lessons

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY content ./content
COPY tests ./tests

RUN mkdir -p /app/data

EXPOSE 8501

CMD ["streamlit", "run", "src/learning_app/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
