FROM python:3.10
WORKDIR /bot
ARG TG_TOKEN=production
ENV TG_TOKEN="${TG_TOKEN}"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD python main.py
