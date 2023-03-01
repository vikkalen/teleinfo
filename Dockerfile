FROM arm32v6/python:3.7-alpine
WORKDIR /usr/src/teleinfo
RUN pip install --no-cache-dir pyserial paho-mqtt pyyaml

COPY . .
CMD [ "python", "./teleinfo.py" ]
