FROM python:buster

RUN pip3 install kafka-python
ADD consumer.py .

CMD ["python3", "consumer.py"]
