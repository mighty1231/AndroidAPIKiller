from __future__ import print_function

import json
import re
import urllib.request
import urllib.error
import ssl
import csv
import time
import datetime
import os

import sys

from androidkit import (
    run_cmd,
    RunCmdError,
    CacheDecorator,
    getConfig
)

auth_header = None
last_req_time = None
GITHUB_ISSUE_FILE_NAME = 'crashanalysis/Github_issues.csv'

class URLParseError(Exception):
    def __init__(self, url):
        super().__init__()
        self.url = url

def parse_url(url):
    # parse URL
    ff = re.search(r'github.com/([^\/]*)/([^\/]*)/issues/(\d+)', url)
    try:
        user, repo, issue_number = ff.groups()
    except AttributeError as e:
        raise URLParseError(url)

    issue_number = int(issue_number)
    return user, repo, issue_number

def parse_issue(user, repo, issue_number):
    data = github_api_rest_get("repos/{}/{}/issues/{}".format(user, repo, issue_number))
    json_data = json.loads(data)

    return json_data

@CacheDecorator
def github_api_rest_get(get_string):
    global last_req_time
    # get_string example: repos/octocat/Hello-World/issues/1
    api_url = "https://api.github.com/{}".format(get_string)

    # github api request recommendation - at least 1 second between two requests
    curtime = datetime.datetime.now()
    if last_req_time is not None:
        interval = (curtime-last_req_time).total_seconds()
        if interval < 1:
            time.sleep(1-interval)

    req = urllib.request.Request(api_url)
    if auth_header is not None:
        req.add_header(*auth_header)
    else:
        print('Warning: there is no auth')
    data = https_open(req)

    last_req_time = datetime.datetime.now()
    return data

def https_open(url_or_req):
    with urllib.request.urlopen(url_or_req, context = ssl._create_unverified_context()) as fp:
        data = fp.read()
    return data

def parse_issue_urls_from_csv():
    issue_urls = []
    cnt_logins = 0
    cnt_not_logins = 0
    error_cnt_parse = 0
    error_cnt_httperror = 0
    with open(GITHUB_ISSUE_FILE_NAME, newline='') as csvf:
        datareader = csv.reader(csvf)
        for i, row in enumerate(datareader):
            if i == 0:
                continue

            issue_url = row[3]
            issue_urls.append(issue_url)

            try:
                user, repo, issue_number = parse_url(issue_url)
            except URLParseError:
                print('ERROR: url parse error', issue_url)
                error_cnt_parse += 1
                continue

            print('URL', user, repo, issue_number)
            try:
                if 'login' in parse_issue(user, repo, issue_number)['body']:
                    cnt_logins += 1
                else:
                    cnt_not_logins += 1
            except urllib.error.HTTPError as e:
                print('ERROR: HTTP error')
                print('  - code =', e.code)
                print('  - msg =', e.msg)
                print('  - hdrs =', e.hdrs)
                print('  - filename =', e.filename)
                error_cnt_httperror += 1
            except urllib.error.URLError as e:
                print('ERROR: URL error')
                print('  - args =', e.args)
                print('  - reason =', e.reason)
                error_cnt_httperror += 1
            except Exception as e:
                print('EXCEPTION')
                print('  - e', e)
                prinT('  - e.args', e.args)
            print('CNT STAT:', cnt_logins, cnt_not_logins, error_cnt_parse, error_cnt_httperror)
    print(cnt_logins, cnt_not_logi, error_cnt_parse, error_cnt_httperror)

def set_auth_header():
    global auth_header

    # My personal token
    # https://taetaetae.github.io/2017/03/02/github-api/
    with open('token.oauth', 'rt') as f:
        personal_access_token = f.read()

    auth_header = ('Authorization', 'token {}'.format(personal_access_token))

def parse_date_from_github_time(timestring):
    # example timestring = 2014-03-31T11:32:44Z
    # YYYY-MM-DDTHH:MM:SSZ
    tm = time.strptime(timestring, "%Y-%m-%dT%H:%M:%SZ")
    assert isinstance(tm, time.struct_time)

    return tm

def get_error_version_apk(user, repo, date_before):
    # Plan A. Try to get released version apk
    # Plan B. Get source and compile new apk
    if not isinstance(date_before, time.struct_time):
        date_before = parse_date_from_github_time(date_before)

    # Plan A
    # get released labels
    try:
        json_releases = json.loads(github_api_rest_get('repos/{}/{}/releases'.format(user, repo)))
    except urllib.error.HTTPError as e:
        # there is no released versions!
        print('ERROR: HTTP error on get repos/{}/{}/releases'.format(user, repo))
        print('  - code =', e.code)
        print('  - msg =', e.msg)

        return None


    after_cnt = 0
    apk_url = None
    release_date = None
    for release_candi in json_releases:
        tm = parse_date_from_github_time(release_candi['published_at'])
        if tm > date_before:
            after_cnt += 1
            continue
        # find apk then out
        assets = release_candi['assets']

        for asset in assets:
            if asset['content_type'] == 'application/vnd.android.package-archive':
                apk_url = asset['browser_download_url']
                print('APK_URL', apk_url)
                release_date = tm

        if apk_url is not None:
            break

    if apk_url:
        return (apk_url, release_date, https_open(apk_url))

    # Plan B
    # raise NotImplementedError
    return None

def mining_apk_and_bug_report():
    issue_urls = []
    current_number = 115
    output_folder = '../data/apk_with_reports'
    with open(GITHUB_ISSUE_FILE_NAME, newline='') as csvf:
        datareader = csv.reader(csvf)
        for i, row in enumerate(datareader):
            if i <= 822:
                continue

            issue_url = row[3]

            try:
                user, repo, issue_number = parse_url(issue_url)
            except URLParseError as e:
                print('ERROR: url parse error', issue_url)
                continue

            print('URL #{}'.format(i), user, repo, issue_number)

            # get issue information
            try:
                issue_data = parse_issue(user, repo, issue_number)

                issue_date = issue_data['created_at']
                issue_body = issue_data['body']

            except urllib.error.HTTPError as e:
                print('ERROR: HTTP error on parse_issue')
                print('  - code =', e.code)
                print('  - msg =', e.msg)
                print('  - filename =', e.filename)
                continue
            except urllib.error.URLError as e:
                print('ERROR: URL error on parse_issue')
                print('  - args =', e.args)
                print('  - reason =', e.reason)
                continue
            except KeyError as e:
                print('KeyError')
                print(json.dumps(issue_data, indent=4, sort_keys=True))
                continue

            # get released apks
            try:
                data = get_error_version_apk(user, repo, issue_date)
            except urllib.error.HTTPError as e:
                print('ERROR: get apk error', user, repo, issue_date)
                data = None
            if data is not None:
                url_path, release_date, apk_data = data
                dir_path = os.path.join(output_folder, '%04d' % current_number)
                os.mkdir(dir_path)

                name = os.path.split(url_path)[1]
                apk_path = os.path.join(dir_path, name) 
                with open(apk_path, 'wb') as f:
                    f.write(apk_data)
                with open(os.path.join(dir_path, 'issue.txt'), 'wt') as f:
                    f.write('// Issue with url {} {} {}\n'.format(user, repo, issue_number))
                    f.write('// Issue date {}\n'.format(issue_date))
                    f.write('// Release date {}\n'.format(release_date))
                    f.write('// sdkversion_info {}\n\n'.format(apk_getsdkversioninfo(apk_path)))
                    f.write(issue_body)

                current_number += 1
            else:
                print('Couldn\'t get apk -', user, repo, issue_date)



def apk_getsdkversioninfo(apk_path):
    # return [minSdkVersion, targetSdkVersion]
    res = run_cmd("{} dump badging {} | grep dkVersion".format(getConfig()['AAPT_PATH'], apk_path))
    pairs = {}
    for line in res.split('\n'):
        if line == '':
            continue
        if ':' not in line:
            continue

        k, v = line.split(':')
        if 'dkVersion' not in k:
            continue

        assert v[0] == v[-1] == '\'', "Expected '##', v {}".format(line)
        pairs[k] = int(v[1:-1])
    
    assert 'sdkVersion' in pairs, pairs
    if 'targetSdkVersion' not in pairs:
        print('Info: there is no targetSdkVersion', pairs)
        return pairs['sdkVersion']
    if len(pairs) > 2:
        print('Info: apk_getsdkversioninfo() - many pairs', pairs)

    return pairs['sdkVersion'], pairs['targetSdkVersion']


if __name__ == "__main__":
    set_auth_header()
    mining_apk_and_bug_report()

