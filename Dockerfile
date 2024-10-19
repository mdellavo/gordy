FROM python:3.13

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONBUFFERED 1

WORKDIR /

RUN apt-get update
RUN apt-get install -y libolm-dev

RUN pip install --upgrade pip
COPY ./requirements.txt /tmp
RUN pip install -r /tmp/requirements.txt


COPY --chown=gordy gordy /gordy

RUN useradd -ms /bin/bash gordy
USER gordy

ENTRYPOINT python3 -m gordy
