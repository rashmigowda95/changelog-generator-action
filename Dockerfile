FROM python:3.8
RUN apt-get update -y
RUN apt-get install -y git
RUN pip install jira
RUN pip install flake8 pytest
COPY changelog_generator.py /changelog_generator.py
RUN pip install PyGithub['integrations']
CMD ["python", "/changelog_generator.py"]
