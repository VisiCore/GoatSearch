#!/usr/bin/env python

import csv
import io
import json
import os
import re
import requests
import socket
import sys
import time
import traceback
import urllib.parse
import warnings

class goatsearch:
    query = None
    sample = None
    page = None
    tenant = None
    workspace = None
    debug = None
    earliest = None
    latest = None
    sid = None
    retry = None
    savedsearch = None

    options = {
        'query': None,
        'sample': 'integer',
        'page': 'integer',
        'tenant': None,
        'workspace': None,
        'debug': 'boolean',
        'earliest': None,
        'latest': None,
        'sid': None,
        'retry': 'integer',
        'savedsearch': None
    }

    truth_values = {
        '1': True, '0': False,
        't': True, 'f': False,
        'true': True, 'false': False,
        'y': True, 'n': False,
        'yes': True, 'no': False
    }

    configuration = {
        'type': 'stateful',
        'generating': True
    }

    ifile = None
    ofile = None

    metadata = None
    searchinfo = None

    maxresultrows = 50000

    records = []
    messages = []

    pending = False

    access_token = False

    v_client_id = False
    v_tenant = False
    v_workspace = False

    headers = False
    search_context = False

    baseuri = False
    job_id = False

    event_log = []

    queue_notice = False
    running_notice = False
    complete_notice = False

    job_complete = False

    total_event_count = 0
    offset = 0
    api_limit = 1000

    can_run = False

    def _get_auth_token(self):
        # TODO: Take this from the .conf/password object
        # TODO: Maybe make the audience configurable?

        storage_passwords = self._splunkd(
            'storage/passwords',
            output_mode = 'json',
            count = -1
        )

        credential_name = "%s:%s:" % (
            self.v_tenant,
            self.v_client_id
        )

        # TODO: Check password exists

        credential = False

        for storage_password in storage_passwords['entry']:
            if storage_password['name'] == credential_name:
                credential = storage_password['content']['clear_password']

        auth_uri = 'https://login.cribl.cloud/oauth/token'

        auth = {
            'grant_type': 'client_credentials',
            'client_id': self.v_client_id,
            'client_secret': credential,
            'audience': 'https://api.cribl.cloud'
        }

        headers = {
            'Content-Type': 'application/json'
        }

        auth_result = requests.post(
            auth_uri,
            json = auth,
            headers = headers
        )

        auth_json = json.loads(auth_result.text)

        if 'access_token' in auth_json.keys():
            self.access_token = auth_json['access_token']

            return True

        # TODO: Fail gracefully
        return False

    def _get_environment(self):
        if not self.tenant:
            kvquery = {
                "default": 1
            }
        elif self.workspace:
            kvquery = {
                "tenant": self.tenant,
                "workspace": self.workspace
            }
        else:
            kvquery = {
                "tenant": self.tenant,
                "workspace": "main"
            }

        env_raw = self._splunkd(
            'storage/collections/data/goatsearch_env_kv',
            query = json.dumps(kvquery)
        )

        for env in env_raw:
            self.v_client_id = env['clientId']
            self.v_tenant = env['tenant']
            self.v_workspace = env['workspace']

            return True

        return False

    def _prepare_event_search(self):
        if self.earliest is None:
            earliest = self.searchinfo['earliest_time']
        else:
            earliest = self.earliest

        if self.latest is None:
            latest = self.searchinfo['latest_time']
        else:
            latest = self.latest

        goatevent = {
            "data": {},
            "_time": time.time()
        }

        self.baseuri = 'https://%s-%s.cribl.cloud/api/v1/m/%s/search/jobs' % (
            self.v_workspace,
            self.v_tenant,
            self.search_context
        )

        if not self.retry:
            retry = 10
        else:
            retry = int(self.retry)

        current = 0

        while current < retry:
            if self.sid:
                self.job_id = self.sid

                return True

            if self.debug:
                devt = {
                    "url": self.baseuri
                }

                self.event_log.append({
                    "_raw": json.dumps(devt),
                    "_time": time.time(),
                    "source": "goatsearch",
                    "sourcetype": "goatsearch:json",
                    "host": "localhost"
                })

            if not self.sample:
                sample_ratio = 1
            else:
                sample_ratio = 1 / int(self.sample)

            job = {
                'query': '%s' % self.query,
                'earliest': earliest,
                'latest': latest,
                'sampleRate': sample_ratio
            }

            # TODO: Require sample to be an integer (and possibly a power of 10)

            search_job = requests.post(
                self.baseuri,
                json = job,
                headers = self.headers
            )

            job_deets = json.loads(search_job.text)

            # TODO: Check that this is an expected { "items: [] } format

            if not 'items' in job_deets:
                devt = {
                    "url": self.baseuri,
                    "message": 'Missing Items',
                    "job": job_deets
                }
   
                # self.write_error(json.dumps(job_deets))
 
                self.event_log.append({
                    "_raw": json.dumps(devt),
                    "_time": time.time(),
                    "source": "goatsearch",
                    "sourcetype": "goatsearch:json",
                    "host": "localhost"
                })
            else:
                for deet in job_deets['items']:
                    if 'id' in deet:
                        self.job_id = deet['id']

                        return True

            current = current + 1
            # time.sleep(5)

        return False

    def _prepare_saved_search(self):
        # TODO: Error if not found.
        savedsearch_uri = 'https://%s-%s.cribl.cloud/api/v1/m/%s/search/saved/%s' % (
            self.v_workspace,
            self.v_tenant,
            self.search_context,
            self.savedsearch
        )

        savedsearch_job = requests.get(
            savedsearch_uri,
            headers = self.headers
        )


        ss_info = json.loads(savedsearch_job.text)

        earliest = "-10m"
        latest = "now"

        query = ""

        for ss in ss_info['items']:
            earliest = ss['earliest']
            latest = ss['latest']
            query = ss['query']

        goatevent = {
            "data": {},
            "_time": time.time()
        }

        self.baseuri = 'https://%s-%s.cribl.cloud/api/v1/m/%s/search/jobs' % (
            self.v_workspace,
            self.v_tenant,
            self.search_context
        )

        if not self.retry:
            retry = 10
        else:
            retry = int(self.retry)

        current = 0

        while current < retry:
            if self.sid:
                self.job_id = self.sid

                return True

            if self.debug:
                devt = {
                    "url": self.baseuri
                }

                self.event_log.append({
                    "_raw": json.dumps(devt),
                    "_time": time.time(),
                    "source": "goatsearch",
                    "sourcetype": "goatsearch:json",
                    "host": "localhost"
                })

            if not self.sample:
                sample_ratio = 1
            else:
                sample_ratio = 1 / int(self.sample)

            job = {
                'query': '%s' % query,
                'earliest': earliest,
                'latest': latest,
                'sampleRate': sample_ratio
            }

            # TODO: Require sample to be an integer (and possibly a power of 10)

            search_job = requests.post(
                self.baseuri,
                json = job,
                headers = self.headers
            )

            job_deets = json.loads(search_job.text)

            # TODO: Check that this is an expected { "items: [] } format

            if not 'items' in job_deets:
                devt = {
                    "url": self.baseuri,
                    "message": 'Missing Items',
                    "job": job_deets
                }
  
                # self.write_error(json.dumps(job_deets))

                self.event_log.append({
                    "_raw": json.dumps(devt),
                    "_time": time.time(),
                    "source": "goatsearch",
                    "sourcetype": "goatsearch:json",
                    "host": "localhost"
                })
            else:
                for deet in job_deets['items']:
                    if 'id' in deet:
                        self.job_id = deet['id']

                        return True

            current = current + 1
            # time.sleep(5)

        return False

    def generate(self):
        if not self.can_run:
            return

        earliest_seen = 0
        latest_seen = 0

        if self.savedsearch and self.savedsearch == "*":
            ssuri = 'https://%s-%s.cribl.cloud/api/v1/m/%s/search/saved' % (
                self.v_workspace,
                self.v_tenant,
                self.search_context
            )

            ss_job = requests.get(
                ssuri,
                headers=self.headers
            )

            ss_deets = json.loads(ss_job.text)

            for ss in ss_deets['items']:
                evt = {
                    '_raw': json.dumps(ss),
                    '_time': time.time(),
                    'index': 'default_search',
                    'source': 'source',
                    'sourcetype': 'saved_search'
                }

                for k, v in ss.items():
                    evt[k]= v

                yield evt

        elif not self.query and not self.sid and not self.savedsearch:
            dataseturi = 'https://%s-%s.cribl.cloud/api/v1/m/%s/search/datasets' % (
                self.v_workspace,
                self.v_tenant,
                self.search_context
            )

            dataset_job = requests.get(
                dataseturi,
                headers=self.headers
            )

            dataset_deets = json.loads(dataset_job.text)

            for dataset in dataset_deets['items']:
                evt = {
                    '_raw': json.dumps(dataset),
                    '_time': time.time(),
                    'index': 'default_search',
                    'source': 'source',
                    'sourcetype': 'dataset'
                }

                for k, v in dataset.items():
                    evt[k]= v

                yield evt
        else:
            if self.query or self.sid:
                self._prepare_event_search()

            if self.savedsearch:
                self._prepare_saved_search()

            if self.page:
                self.api_limit = int(self.page)

            if not self.job_id:
                for evt in self.event_log:
                    yield evt

                return

            while not self.job_complete:
                status_uri = '%s/%s/status' % (
                    self.baseuri,
                    self.job_id
                )

                status = requests.get(
                    status_uri,
                    headers = self.headers
                )

                if self.debug:
                    devt = {
                        "url": status_uri,
                        "status": json.loads(status.text)
                    }

                    yield {
                        "_raw": json.dumps(devt),
                        "_time": time.time(),
                        "source": "goatsearch",
                        "sourcetype": "goatsearch:json",
                        "host": "localhost"
                    }

                # TODO: Make sure that this is an expected { "items: [] } format

                statuses = json.loads(status.text)

                if not 'items' in statuses:
                    yield { '_raw': json.dumps(statuses) }
                    return

                for job_status in statuses['items']:
                    # Is statuses a word? Stati?

                    # TODO: Add some sort of status notifier or job duration. Maybe we can hijack the error mechanism for this.
                    #       ... if I can that would be my most advanced UI hijack to date...

                    if 'totalEventCount' in job_status and job_status['totalEventCount'] > self.total_event_count:
                        total_event_count = job_status['totalEventCount']

                    if 'status' in job_status and job_status['status'] == 'completed':
                        self.job_complete = True

                        if not self.complete_notice:
                            self.messages = []
                            self.write_info('Cribl Search job complete.')

                    if 'status' in job_status and job_status['status'] == 'queued' and not self.queue_notice:
                        self.messages = []
                        self.write_warning('Waiting for queued Cribl Search job to start.')
                        self.queue_notice = True

                    if 'status' in job_status and job_status['status'] == 'running' and not self.running_notice:
                        self.messages = []
                        self.write_info('Cribl Search job is running.')
                        self.running_notice = True

                # TODO: Do something when no results

                # TODO: Do something if the job fail

                collecting = self.job_complete

                self.flush()

                while collecting:
                    collecting = False

                    results_uri = '%s/%s/results?limit=%s&offset=%s' % (
                        self.baseuri,
                        self.job_id,
                        self.api_limit,
                        self.offset
                    )

                    # TODO: We have to account for the fact these results may be out of time-order.

                    self.headers['Accept'] = 'application/x-nd-json'

                    results_chunk = requests.get(
                        results_uri,
                        headers = self.headers,
                        stream = True
                    )

                    for line in results_chunk.iter_lines():
                        event = json.loads(line)

                        if 'totalEventCount' in event:
                            if self.debug:
                                devt = {
                                    "url": results_uri,
                                    "results": event
                                }

                                # if results_chunk:
                                #    devt["linecount"] = len(results_chunk.text.split("\n"))

                                yield {
                                    "_raw": json.dumps(devt),
                                    "_time": time.time(),
                                    "source": "goatsearch",
                                    "sourcetype": "goatsearch:json",
                                    "host": "localhost"
                                }

                            if 'totalEventCount' in event.keys():
                                self.total_event_count = event['totalEventCount']
                        else:
                            if not '_time' in event or event['_time'] is None:
                                event['_time'] = time.time()

                            if event['_time'] < earliest_seen or earliest_seen == 0:
                                earliest_seen = event['_time']

                            if event['_time'] > latest_seen or latest_seen == 0:
                                latest_seen = event['_time']

                            evt = {
                                '_raw': event['_raw'] if '_raw' in event else json.dumps(event),
                                '_time': event['_time'] if '_time' in event else time.time(),
                                'index': event['dataset'] if 'dataset' in event else 'unknown',
                                'source': event['source'] if 'source' in event else 'unknown',
                                'sourcetype': event['datatype'] if 'datatype' in event else 'unknown'
                            }

                            if 'instance' in event and 'datatype' in event and event['datatype'] == 'cribl_json':
                                evt['host'] = event['instance']

                            for k, v in event.items():
                                if k[0] != '_':
                                    evt[k] = v

                            yield evt

                            self.offset = self.offset + 1
                            collecting = True

                    self.flush()

            if earliest_seen > 0:
                self.searchinfo['earliest_time'] = earliest_seen

            if latest_seen > 0 and latest_seen == 0:
                self.searchinfo['latest_time'] = latest_seen

            if self.debug:
                for evt in self.event_log:
                    yield evt

    def prepare(self):
        user = self.searchinfo['username']

        user_info = self._splunkd(
            'authentication/users/%s' % urllib.parse.quote(user.lower(), safe=''),
            output_mode = 'json'
        )

        caps = user_info['entry'][0]['content']['capabilities']

        if not 'goatsearch_user' in caps:
            self.write_error("You must have the 'goatsearch_user' capability to use this command.")
            return

        self.can_run = True

        self.messages = []
        self.write_info("Getting environment settings.")

        self._get_environment()

        self.messages = []
        self.write_info("Getting authentication token.")
        self._get_auth_token()

        self.headers = {
            'Authorization': 'Bearer %s' % self.access_token,
            'Content-Type': 'application/json'
        }

        # TODO: Placeholder. This is hard-coded in the API documentation but the format suggests
        #       it could be a variable for a coming feature.
        self.search_context = 'default_search'

    def write_info(self, message):
        self.messages.append(['INFO', message])

    def write_warning(self, message):
        self.messages.append(['WARN', message])

    def write_error(self, message):
        self.messages.append(['ERROR', message])

    def flush(self):
        if not self.records and not self.messages:
            return

        self._send(False)
        self._read_execute()

    def run(self, ifile, ofile):
        self.ifile = ifile
        self.ofile = ofile

        try:
            self._process()
        except BrokenPipeError:
            os._exit(0)
        except Exception as error:
            traceback.print_exc(file=sys.stderr)

            self.write_error('%s: %s' % (type(error).__name__, error))

            if self.pending:
                self._send(True)

            sys.exit(1)

    def _process(self):
        chunk = self._read_chunk()

        if chunk is None:
            return

        metadata, body = chunk

        if metadata.get('action') != 'getinfo':
            raise RuntimeError('Expected getinfo action, not %s' % metadata.get('action'))

        self.pending = 'getinfo'

        self.metadata = metadata
        self.searchinfo = metadata['searchinfo']

        self.searchinfo['earliest_time'] = float(self.searchinfo['earliest_time'])
        self.searchinfo['latest_time'] = float(self.searchinfo['latest_time'])

        if self.searchinfo.get('maxresultrows'):
            self.maxresultrows = int(self.searchinfo['maxresultrows'])

        if not self._parse_options():
            self._send()
            sys.exit(1)

        if not metadata.get('preview'):
            self.prepare()

        self._send()
        self._read_execute()

        for record in self.generate():
            self.records.append(record)

            if len(self.records) >= self.maxresultrows:
                self.flush()

        self._send(True)

        while self._read_chunk() is not None:
            self._send(True)

    def _parse_options(self):
        valid = True

        for arg in self.searchinfo.get('args') or []:
            result = arg.split('=', 1)

            if len(result) == 1:
                continue

            name, value = result

            if name not in self.options:
                self.write_error('Unrecognized option: %s=%s' % (name, value))
                valid = False
                continue

            try:
                if self.options[name] == 'integer':
                    value = int(value)
                elif self.options[name] == 'boolean':
                    value = self.truth_values[value.lower()]
            except (KeyError, ValueError):
                self.write_error('Illegal value: %s=%s' % (name, value))
                valid = False
                continue

            setattr(self, name, value)

        return valid

    def _splunkd(self, path, **params):
        uri = '%s/servicesNS/nobody/%s/%s' % (
            self.searchinfo['splunkd_uri'],
            urllib.parse.quote(self.searchinfo['app'], safe=''),
            path
        )

        session = requests.Session()
        session.trust_env = False

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')

            response = session.get(
                uri,
                params = params,
                headers = {
                    'Authorization': 'Splunk %s' % self.searchinfo['session_key']
                },
                verify = False
            )

        response.raise_for_status()

        return json.loads(response.text)

    def _read_chunk(self):
        header = self.ifile.readline()

        if not header:
            return None

        match = re.match(r'chunked\s+1.0\s*,\s*(\d+)\s*,\s*(\d+)\s*\n', header.decode('utf-8'))

        if match is None:
            raise RuntimeError('Failed to parse transport header: %s' % header)

        metadata_length = int(match.group(1))
        body_length = int(match.group(2))

        metadata = {}

        if metadata_length > 0:
            metadata = json.loads(self.ifile.read(metadata_length).decode('utf-8'))

        body = self.ifile.read(body_length)

        return metadata, body

    def _read_execute(self):
        chunk = self._read_chunk()

        if chunk is None:
            sys.exit(0)

        metadata, body = chunk

        if metadata.get('action') != 'execute':
            raise RuntimeError('Expected execute action, not %s' % metadata.get('action'))

        self.pending = 'execute'

    def _send(self, finished=None):
        if self.pending == 'getinfo':
            metadata = dict(self.configuration)
        else:
            metadata = {
                'finished': finished
            }

        if self.messages:
            metadata['inspector'] = {
                'messages': self.messages
            }

        metadata = json.dumps(metadata, separators=(',', ':')).encode('utf-8')
        body = self._encode_records().encode('utf-8')

        self.records = []
        self.messages = []
        self.pending = False

        self.ofile.write(('chunked 1.0,%s,%s\n' % (len(metadata), len(body))).encode('utf-8'))
        self.ofile.write(metadata)
        self.ofile.write(body)
        self.ofile.flush()

    def _encode_records(self):
        if not self.records:
            return ''

        fieldnames = {}

        for record in self.records:
            fieldnames.update(dict.fromkeys(record))

        buffer = io.StringIO()
        writer = csv.writer(buffer)

        header = []

        for fieldname in fieldnames:
            header.append(fieldname)
            header.append('__mv_%s' % fieldname)

        writer.writerow(header)

        for record in self.records:
            row = []

            for fieldname in fieldnames:
                row.extend(self._encode_value(record.get(fieldname)))

            writer.writerow(row)

        return buffer.getvalue()

    def _encode_value(self, value):
        if isinstance(value, (list, tuple)):
            if len(value) > 1:
                items = ['' if item is None else self._encode_scalar(item) for item in value]

                return '\n'.join(items), ';'.join('$%s$' % item.replace('$', '$$') for item in items)

            if len(value) == 0:
                return None, None

            value = value[0]

        if value is None:
            return None, None

        return self._encode_scalar(value), None

    def _encode_scalar(self, value):
        if isinstance(value, bool):
            return str(value.real)

        if isinstance(value, str):
            return value

        if isinstance(value, bytes):
            return value.decode('utf-8', errors='backslashreplace')

        if isinstance(value, (int, float)):
            return str(value)

        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, separators=(',', ':'))

        return repr(value)

if __name__ == '__main__':
    goatsearch().run(sys.stdin.buffer, sys.stdout.buffer)
