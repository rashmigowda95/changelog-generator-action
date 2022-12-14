FROM python:3
RUN apt-get update -y
RUN apt-get install -y git
COPY changelog_generator.py /changelog_generator.py
RUN pip install PyGithub['integrations']
CMD ["python", "/changelog_generator.py"]
