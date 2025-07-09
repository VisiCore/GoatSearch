#!/usr/bin/env python

import json
import os
import re
import requests
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from splunklib.searchcommands import \
    dispatch, GeneratingCommand, Configuration, Option, validators

@Configuration(local=True, type='events', retainsevents=True)
class goatsearch(GeneratingCommand):
    query = Option(require=False, validate=None)
    sample = Option(require=False, validate=None)
    page = Option(require=False, validate=validators.Integer())
    tenant = Option(require=False, validate=None)
    workspace = Option(require=False, validate=None)
    debug = Option(require=False, validate=validators.Boolean())

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
    api_limit = 200

    def _get_auth_token(self):
        # TODO: Take this from the .conf/password object
        # TODO: Maybe make the audience configurable?

        storage_passwords = self.service.storage_passwords

        credential_name = "%s:%s:" % (
            self.v_tenant,
            self.v_client_id
        )

        # TODO: Check password exists

        credential = False

        for storage_password in storage_passwords.list():
            if storage_password.name == credential_name:
                credential = storage_password['clear_password']

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

        collection = self.service.kvstore['goatsearch_env_kv']

        env_raw = collection.data.query(query=kvquery)

        for env in env_raw:
            self.v_client_id = env['clientId']
            self.v_tenant = env['tenant']
            self.v_workspace = env['workspace']

            return True

        return False

    def _prepare_event_search(self):
        earliest = self.metadata.searchinfo.earliest_time
        latest = self.metadata.searchinfo.latest_time

        goatevent = {
            "data": {},
            "_time": time.time()
        }

        self.baseuri = 'https://%s-%s.cribl.cloud/api/v1/m/%s/search/jobs' % (
            self.v_workspace,
            self.v_tenant,
            self.search_context
        )

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
            'query': 'cribl %s' % self.query,
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

        for deet in job_deets['items']:
            if 'id' in deet:
                self.job_id = deet['id']

        # TODO: Check that we actually retrieved a job ID

    def generate(self):
        if not self.query:
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

                for job_status in statuses['items']:
                    # Is statuses a word? Stati?

                    # TODO: Add some sort of status notifier or job duration. Maybe we can hijack the error mechanism for this.
                    #       ... if I can that would be my most advanced UI hijack to date...

                    if 'totalEventCount' in job_status and job_status['totalEventCount'] > self.total_event_count:
                        total_event_count = job_status['totalEventCount']

                    if 'status' in job_status and job_status['status'] == 'completed':
                        self.job_complete = True

                        if not self.complete_notice:
                            self._record_writer._inspector['messages'] = []
                            self.write_info('Cribl Search job complete.')

                    if 'status' in job_status and job_status['status'] == 'queued' and not self.queue_notice:
                        self._record_writer._inspector['messages'] = []
                        self.write_warning('Waiting for queued Cribl Search job to start.')
                        self.queue_notice = True

                    if 'status' in job_status and job_status['status'] == 'running' and not self.running_notice:
                        self._record_writer._inspector['messages'] = []
                        self.write_info('Cribl Search job is running.')
                        self.running_notice = True

                # TODO: Do something when no results

                # TODO: Do something if the job fail

                collecting = True

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

                        if '_raw' in event:
                            evt = {
                                '_raw': event['_raw'],
                                '_time': event['_time'],
                                'index': event['dataset'],
                                'source': event['source'],
                                'sourcetype': event['datatype']
                            }

                            raw_dict = json.loads(event['_raw'])

                            for k, v in raw_dict.items():
                                evt[k]= v

                            yield evt

                            self.offset = self.offset + 1
                            collecting = True
                        else:
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

    def prepare(self):
        self._record_writer._inspector['messages'] = []
        self.write_info("Getting environment settings.")

        self._get_environment()

        self._record_writer._inspector['messages'] = []
        self.write_info("Getting authentication token.")
        self._get_auth_token()

        self.headers = {
            'Authorization': 'Bearer %s' % self.access_token,
            'Content-Type': 'application/json'
        }

        # TODO: Placeholder. This is hard-coded in the API documentation but the format suggests
        #       it could be a variable for a coming feature.
        self.search_context = 'default_search'

        if self.query:
            self._prepare_event_search()

        if self.page:
            self.api_limit = int(self.page)

dispatch(goatsearch, sys.argv, sys.stdin, sys.stdout, __name__)
