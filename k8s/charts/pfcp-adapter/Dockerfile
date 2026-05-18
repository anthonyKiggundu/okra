FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY pfcp_adapter.py .

EXPOSE 8081/udp
EXPOSE 8081

CMD ["uvicorn", "pfcp_adapter:app", "--host", "0.0.0.0", "--port", "8081"]

