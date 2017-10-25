FROM python:3

WORKDIR /usr/src/app/src

COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt && \
    rm /requirements.txt

CMD [ "python", "./main.py" ]
