#!/usr/bin/env python

import json
import os
import re
import requests
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from splunklib.searchcommands import \
    dispatch, GeneratingCommand, Configuration, Option, validators

@Configuration(local=True)
class goatsearch(GeneratingCommand):
    query = Option(require=True, validate=None)
    sample = Option(require=False, validate=None)
    page = Option(require=False, validate=None)
    tenant = Option(require=True, validate=None)
    workspace = Option(require=False, validate=None)

    def _get_auth_token(self, tenant, client_id):
        # TODO: Take this from the .conf/password object
        # TODO: Maybe make the audience configurable?

        storage_passwords = self.service.storage_passwords

        credential_name = "%s:%s:" % (
            tenant,
            client_id
        )

        # TODO: Check password exists

        credential = False

        for storage_password in storage_passwords.list():
            if storage_password.name == credential_name:
                credential = storage_password['clear_password']

        auth_uri = 'https://login.cribl.cloud/oauth/token'

        auth = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
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
            return auth_json['access_token']

        return False

    def _get_environment(self):
        if self.workspace:
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
                return env['clientId'], env['tenant'], env['workspace']

            return False

    def generate(self):
        # TODO: Make sure we got something
        client_id, tenant, workspace = self._get_environment()

        earliest = self.metadata.searchinfo.earliest_time
        latest = self.metadata.searchinfo.latest_time

        # TODO: Placeholder. This is hard-coded in the API documentation but the format suggests
        #       it could be a variable for a coming feature.
        search_context = 'default_search'

        # TODO: Fail gracefully if 401.
        token = self._get_auth_token(tenant, client_id)

        headers = {
            'Authorization': 'Bearer %s' % token,
            'Content-Type': 'application/json'
        }

        baseuri = 'https://%s-%s.cribl.cloud/api/v1/m/%s/search/jobs' % (
            workspace,
            tenant,
            search_context
        )

        if not self.sample:
            sample_ratio = 1
        else:
            sample_ratio = self.sample

        job = {
            'query': 'cribl %s' % self.query,
            'earliest': earliest,
            'latest': latest,
            'sampleRate': sample_ratio
        }

        # TODO: Require sample to be an integer (and possibly a power of 10)

        search_job = requests.post(
            baseuri,
            json = job,
            headers = headers
        )

        job_deets = json.loads(search_job.text)

        job_id = False

        # TODO: Check that this is an expected { "items: [] } format

        for deet in job_deets['items']:
            if 'id' in deet:
                job_id = deet['id']


        # TODO: Check that we actually retrieved a job ID

        job_complete = False

        total_event_count = 0

        while not job_complete:
            status_uri = '%s/%s/status' % (
                baseuri,
                job_id
            )

            status = requests.get(
                status_uri,
                headers = headers
            )

            # TODO: Make sure that this is an expected { "items: [] } format

            statuses = json.loads(status.text)

            for job_status in statuses['items']:
                # Is statuses a word? Stati?

                # TODO: Add some sort of status notifier or job duration. Maybe we can hijack the error mechanism for this.
                #       ... if I can that would be my most advanced UI hijack to date...

                if 'status' in job_status and job_status['status'] == 'completed':
                    job_complete = True

        # TODO: Do something when no results

        # TODO: Do something if the job fail

        offset = 0

        if self.page:
            api_limit = int(self.page)
        else:
            api_limit = 200

        all_collected = False

        while not all_collected:
            results_uri = '%s/%s/results?limit=%s&offset=%s' % (
                baseuri,
                job_id,
                api_limit,
                offset
            )

            # TODO: We have to account for the fact these results may be out of time-order.

            headers['Accept'] = 'application/x-nd-json'

            results_chunk = requests.get(
                results_uri,
                headers = headers,
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
                else:
                    if 'totalEventCount' in event.keys():
                        total_event_count = event['totalEventCount']

            if offset >= total_event_count:
                all_collected = True

            offset = offset + api_limit

dispatch(goatsearch, sys.argv, sys.stdin, sys.stdout, __name__)
