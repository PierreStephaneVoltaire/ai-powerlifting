FROM python:3.12-slim
WORKDIR /opt/powerlifting
COPY services/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services ./services
RUN useradd -m -u 10001 service
USER service
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "uvicorn", "services.app:app", "--host", "0.0.0.0", "--port", "8000"]
