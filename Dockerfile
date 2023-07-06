FROM python:3.8-slim-buster

ENV LOG_LEVEL=WARNING
ENV DEVICES=
ENV POLL_INTERVAL=
ENV PORT=

COPY docker_entrypoint.sh /

WORKDIR /app

COPY . .
RUN pip3 install .

ENTRYPOINT sh /docker_entrypoint.sh
