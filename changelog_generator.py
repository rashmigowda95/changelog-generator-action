#!/usr/bin/env python3

import re
import shlex
import subprocess
import time
import sys
import os
from jira import JIRA, JIRAError
from datetime import datetime
from github import Github


# ~^~^~^~ user config ~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~^~

# point to your jira installation
jira_server = 'https://rashmingowda95.atlassian.net'

"""
configure authentication, see jira module docs for more auth modes
https://jira.readthedocs.io/en/latest/examples.html#authentication
"""
jira = JIRA(server=(jira_server), basic_auth=('rashmingowda95', 'RAMYAsn.90'))

changelogFilename = "CHANGELOG.md"

# configure possible issue types
bugTypes = ['Bug', 'InstaBug']
featureTypes = ['Story', 'Task']
refactoringTypes = ['Refactoring']
ignoredTypes = ['Sub-task']

# if you building different types (alpha,beta,production) and
# want to differ in the changelog, specify default here and/or
# pass it as first argument
buildType = "Release"
if len(sys.argv) > 1:
    buildType = sys.argv[1]

# generate markdown with hyperlinks
render_link = False

# ^-^-^ END user config ^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^-^


project_format = r'[A-Z][A-Z\d]+'
git_cmd = 'git log $(git describe --abbrev=0 --tag)..HEAD --format="%s"'

projects = []
issues = []
added = []
bugs = []


def load_properties(filepath, sep='=', comment_char='#'):
    """
    parse version this example uses a gradle property file
    load_properties taken from:
    https://stackoverflow.com/questions/3595363/properties-file-in-python-similar-to-java-properties#8220790
    """
    props = {}
    with open(filepath, "rt") as f:
        for line in f:
            elements = line.strip()
            if elements and not elements.startswith(comment_char):
                key_value = elements.split(sep)
                key = key_value[0].strip()
                value = sep.join(key_value[1:]).strip().strip('"')
                props[key] = value
    return props


def set_fixVersions(issue, version):
    fixVersions = []
    for existing_version in issue.fields.fixVersions:
        fixVersions.append({'name': existing_version.name})
    fixVersions.append({'name': version.name})
    try:
        issue.update(fields={'fixVersions': fixVersions})
    except JIRAError as e:
        print(e.status_code, e.text, issue.key)


def scan_for_tickets():
    issue_pattern = r'{}-[\d]+'.format(project_format)
    try:
        result = subprocess.check_output(git_cmd, shell=True)
    except subprocess.CalledProcessError as e:
        print("Calledprocerr")
    for line in result.decode('utf-8').splitlines():
        issue_id_match = re.search(issue_pattern, line)
        if issue_id_match:
            found_issue_id = issue_id_match.group()
            issues.append(found_issue_id)
            collect_project(found_issue_id)
    return list(set(issues))


def collect_project(issue_id):
    project_id = issue_id.split("-", 1)[0]
    if project_id not in projects:
        projects.append(project_id)


def create_versions(release_version):
    for project in projects:
        version_exists = False
        try:
            versions = jira.project_versions(project)
        except JIRAError as e:
            print("Could not find project: " + project)
            continue

        for version in versions:
            if version.name == release_version.name:
                version_exists = True
                break

        sys.stdout.write('version ' + release_version.name
                         + ' in project ' + project)
        if(version_exists):
            print(' exists - not creating one')
        else:
            print(' not found - creating it!')
            try:
                jira.create_version(release_version.name, project).name
            except JIRAError as e:
                print('Not able to create version for: ' + project
                      + '! Please check if script user has admin rights')
                pass


def render(issue):
    if(render_link):
        issue_url = jira_server + "/browse/" + issue.key
        issue_line = (" * [" + issue.key + "](" + issue_url + ") "
                      + issue.fields.summary + "\n")
    else:
        issue_line = " * " + issue.key + " " + issue.fields.summary + "\n"
    return issue_line


props = load_properties('gradle.properties')
release = type('', (), {})()
release.name = (props['versionMajor'] + '.'
                + props['versionMinor']
                + '.' + props['versionPatch'])

issues = scan_for_tickets()
create_versions(release)
for issueCode in issues:
    try:
        issue = jira.issue(issueCode)
    except JIRAError as e:
        print(issueCode + "not found")
    set_fixVersions(issue, release)
    if issue.fields.issuetype.name in bugTypes:
        bugs.append(issue)
    elif issue.fields.issuetype.name in ignoredTypes:
        # ignore issue type; continue with the next one.
        continue
    elif issue.fields.issuetype.name in featureTypes:
        added.append(issue)
    else:
        added.append(issue)

changelogHeading = "## [" + release.name + "] " + buildType + " " \
                    + props['buildNumber'] + " - " \
                    + datetime.today().strftime("%Y-%m-%d") + "\n"
changelog = ""
if added:
    changelog += "### Added\n"
    for issue in added:
        changelog += render(issue)
    changelog += "\n"
if bugs:
    changelog += "### Fixed\n"
    for issue in bugs:
        changelog += render(issue)

print(changelog)



def github_login(ACCESS_TOKEN, REPO_NAME):
    '''
    Use Pygithub to login to the repository

    Args:
        ACCESS_TOKEN (string): github Access Token
        REPO_NAME (string): repository name

    Returns:
        github.Repository.Repository: object represents the repo

    References:
    ----------
    [1]https://pygithub.readthedocs.io/en/latest/github_objects/Repository.html#github.Repository.Repository
    '''
    g = Github(ACCESS_TOKEN)
    repo = g.get_repo(REPO_NAME)
    return repo


def get_inputs(input_name):
    '''
    Get a Github actions input by name

    Args:
        input_name (str): input_name in workflow file

    Returns:
        string: action_input

    References
    ----------
    [1] https://help.github.com/en/actions/automating-your-workflow-with-github-actions/metadata-syntax-for-github-actions#example
    '''
    return os.getenv('INPUT_{}'.format(input_name).upper())


def write_changelog(repo, changelog, path, commit_message):
    '''
    Write contributors list to file if it differs

    Args:
        repo (github.Repository.Repository): object represents the repo
        changelog (string): content of changelog
        path (string): the file to write
        commit_message (string): commit message
    '''
    contents = repo.get_contents(path)
    repo.update_file(contents.path, commit_message, changelog, contents.sha)


def get_commit_log():
    output = subprocess.check_output(
        shlex.split('git log --pretty=%s --color'), stderr=subprocess.STDOUT)
    output = output.decode('utf-8')
    output = output.split('\n')
    return output


def strip_commits(commits):
    # feat, fix, refactor, test
    output = []
    for line in commits:
        if re.findall(r'^(feat|fix|refactor|test|ci)', line):
            output.append(line)
    return output


def overwrite_changelog(commits):
    print("Going to write the following commits:\n{}".format(commits))
    changelog = ''
    with open("/github/home/CHANGELOG.md", "w+") as file:
        file.write('# Changelog\n\n\n## Features\n\n')
        changelog += '# Changelog\n\n\n## Features\n\n'
        for feat in commits:
            if re.findall(r'^feat', feat):
                file.write('* {}\n'.format(feat))
                changelog += '* {}\n'.format(feat)
        file.write('\n## Bugs\n\n')
        changelog += '\n## Bugs\n\n'
        for fix in commits:
            if re.findall(r'^fix', fix):
                file.write('* {}\n'.format(fix))
                changelog += '* {}\n'.format(fix)
        file.write('\n## Other\n\n')
        changelog += '\n## Other\n\n'
        for other in commits:
            if re.findall(r'^(refactor|test|ci)', other):
                file.write('* {}\n'.format(other))
                changelog += '* {}\n'.format(other)
        file.write(
            '\n\n\n> Changelog generated through the projects\' GitHub Actions.'
        )
        changelog += '\n\n\n> Changelog generated through the projects\' GitHub Actions.'
        file.close()
    return changelog


def main():
    ACCESS_TOKEN = get_inputs('ACCESS_TOKEN')
    REPO_NAME = get_inputs('REPO_NAME')
    PATH = get_inputs('PATH')
    COMMIT_MESSAGE = get_inputs('COMMIT_MESSAGE')
    commits = get_commit_log()
    commits = strip_commits(sorted(commits))
    changelog = overwrite_changelog(commits)
    repo = github_login(ACCESS_TOKEN, REPO_NAME)
    write_changelog(repo, changelog, PATH, COMMIT_MESSAGE)


if __name__ == '__main__':
    main()
