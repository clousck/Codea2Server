FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
# Las dependencias van antes que el código: cambiar el código no las reinstala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python3", "server.py"]
