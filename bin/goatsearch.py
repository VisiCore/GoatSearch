#!/usr/bin/env python

import json
import os
import re
import requests
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

CRIBL_WORKSPACE = 'main'
CRIBL_TENANT = 'kind-hypatia-1buyrym'
CRIBL_CLIENT_ID = '6wmf3QSGoiA3bZWhPBj8b1hHXyQR0Q3n'
CRIBL_TOKEN = 'Nue7v5WXSdR6ZVd3WWNYt9eCeao8vhZ_uAikMB8hLBYOG9NMOuUY5iG_h6PF3-ru'


from splunklib.searchcommands import \
    dispatch, GeneratingCommand, Configuration, Option, validators

@Configuration(local=True)
class goatsearch(GeneratingCommand):
    query = Option(require=True, validate=None)
    sample = Option(require=False, validate=None)

    def _get_auth_token(self):
        # TODO: Take this from the .conf/password object
        # TODO: Maybe make the audience configurable?

        auth_uri = 'https://login.cribl.cloud/oauth/token'

        auth = {
            'grant_type': 'client_credentials',
            'client_id': CRIBL_CLIENT_ID,
            'client_secret': CRIBL_TOKEN,
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

    def generate(self):
        earliest = self.metadata.searchinfo.earliest_time
        latest = self.metadata.searchinfo.latest_time

        # TODO: Placeholder. This is hard-coded in the API documentation but the format suggests
        #       it could be a variable for a coming feature.
        search_context = 'default_search'

        # TODO: Fail gracefully if 401.
        token = self._get_auth_token()

        headers = {
            'Authorization': 'Bearer %s' % token,
            'Content-Type': 'application/json'
        }

        baseuri = 'https://%s-%s.cribl.cloud/api/v1/m/%s/search/jobs' % (
            CRIBL_WORKSPACE,
            CRIBL_TENANT,
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

                    # yield {
                    #     '_raw': job_status,
                    #     'bear': 1
                    # }

        # TODO: Do something when no results

        # TODO: Do something if the job fail

        # TODO: Maybe make these options?
        offset = 0
        limit = 200

        all_collected = False

        while not all_collected:
            results_uri = '%s/%s/results?limit=%s&offset=%s' % (
                baseuri,
                job_id,
                limit,
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

                    # evt['dict'] = raw_dict

                    for k, v in raw_dict.items():
                        evt[k]= v

                    yield evt
                else:
                    yield { '_raw': event, 'gristen': 1 }

dispatch(goatsearch, sys.argv, sys.stdin, sys.stdout, __name__)
