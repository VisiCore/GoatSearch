#!/usr/bin/env python

import json
import os
import re
import requests
import socket
import sys
import time
import atexit
import threading
from queue import Queue, Empty
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from splunklib.searchcommands.internals import RecordWriterV2
from splunklib.searchcommands import \
    dispatch, GeneratingCommand, Configuration, Option, validators


@Configuration(local=True, type='streaming', distributed=False)
class goatsearch(GeneratingCommand):
    query = Option(require=False, validate=None)
    sample = Option(require=False, validate=validators.Integer())
    page = Option(require=False, validate=validators.Integer())
    tenant = Option(require=False, validate=None)
    workspace = Option(require=False, validate=None)
    debug = Option(require=False, validate=validators.Boolean())
    earliest = Option(require=False, validate=None)
    latest = Option(require=False, validate=None)
    sid = Option(require=False, validate=None)
    retry = Option(require=False, validate=validators.Integer())

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

    can_run = False

    # Track user stop requests
    _finalizing = False

    def init_messages(self):
        """ Initialize the messages array in the inspector. """
        assert isinstance(self._record_writer, RecordWriterV2)
        if 'messages' not in self._record_writer._inspector:
            self._record_writer._inspector['messages'] = []

    def set_prop_on_file_create(self, file_path, obj, attr_name):
        """ Set an attribute on an object to True when a file is created. 
        Used to monitor for the 'finalize' file in the dispatch directory. """
        def monitor():
            try:
                while not getattr(obj, attr_name) and not os.path.exists(file_path):
                    time.sleep(0.25)
                if os.path.exists(file_path):
                    print(f"File created: {file_path}, setting {type(obj).__name__}.{attr_name}=True", file=sys.stderr)
                    setattr(obj, attr_name, True)
            except Exception as e:
                print(f"Exception in monitor thread: {e}", file=sys.stderr)
        threading.Thread(target=monitor, daemon=True).start()
        # Force the attribute to True on exit to avoid hanging threads
        atexit.register(lambda: setattr(obj, attr_name, True))

    # Emit messages at the speed they are produced
    def set_flush_size(self, flush_size: int=1000):
        """ Set the flush size for the record writer. """
        assert isinstance(self._record_writer, RecordWriterV2)
        if self._record_writer._maxresultrows != flush_size:
            self._record_writer._maxresultrows = flush_size
            print(f"Set flush size to {flush_size}", file=sys.stderr)

    @staticmethod
    def format_timestamp(ts):
        """ Format an epoch timestamp to a human-readable string. """
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

    # Try to make the timeliner work correctly
    def update_earliest_latest(self, earliest, latest):
        """ Update the earliest and latest times in the search metadata. """
        if earliest > 0:
            try:
                earliest_ts = float(earliest)
                self._metadata.searchinfo.earliest_time = earliest
                self.search_results_info.api_et = earliest
                self.search_results_info.search_et = earliest
                self.search_results_info.startTime = earliest
            except ValueError:
                print(f"Invalid earliest time: {earliest}", file=sys.stderr)

        if latest > 0:
            try:
                latest_ts = float(latest)
                self._metadata.searchinfo.latest_time = latest_ts
                self.search_results_info.api_lt = latest_ts
                self.search_results_info.search_lt = latest_ts
                self.search_results_info.endTime = latest_ts
                #self.search_results_info.now
            except ValueError:
                print(f"Invalid latest time: {latest}", file=sys.stderr)

    def _get_auth_token(self):
        """ Get an OAuth token from Cribl Cloud. """
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

        if self.earliest is None:
            earliest = self.metadata.searchinfo.earliest_time
        else:
            earliest = self.earliest

        if self.latest is None:
            latest = self.metadata.searchinfo.latest_time
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
            time.sleep(5)

        return False

    def generate(self):
        if not self.can_run:
            return
        
        # Set the flush size to 1 yielded event
        self.set_flush_size(1)

        # Monitor for the finalize file in the dispatch directory
        # If the file appears, the user clicked stop. Sets self._finalizing to True
        self.set_prop_on_file_create(
            os.path.join(self.metadata.searchinfo.dispatch_dir, 'finalize'), self, '_finalizing')

        earliest_seen = 0
        latest_seen = 0

        if not self.query and not self.sid:
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

            if self.page:
                self.api_limit = int(self.page)

            if not self.job_id:
                for evt in self.event_log:
                    yield evt

                return

            latest_status: str = ""
            while not self.job_complete and not getattr(self, '_finalizing', False):
                status_uri = '%s/%s/status' % (
                    self.baseuri,
                    self.job_id
                )

                status_response = requests.get(
                    status_uri,
                    headers = self.headers
                )

                statuses = json.loads(status_response.text)
                status_obj = statuses.get('items', [])[0] if 'items' in statuses else {}
                latest_status = status_obj.get('status', latest_status)

                if self.debug:
                    devt = {
                        "_raw": json.dumps({
                            "url": status_uri,
                            "status": status_obj
                        }),
                        "_time": time.time(),
                        "source": "goatsearch",
                        "sourcetype": "goatsearch:json",
                        "host": "localhost",
                        **status_obj
                    }
                    yield devt

                # TODO: Make sure that this is an expected { "items: [] } format
                if not 'items' in statuses:
                    yield { '_raw': json.dumps(statuses) }
                    return

                for job_status in statuses['items']:
                    # Is statuses a word? Stati?
                    latest_status = job_status.get('status', latest_status)
                    # TODO: Add some sort of status notifier or job duration. Maybe we can hijack the error mechanism for this.
                    #       ... if I can that would be my most advanced UI hijack to date...

                    if 'totalEventCount' in job_status and job_status['totalEventCount'] > self.total_event_count:
                        total_event_count = job_status['totalEventCount']

                    if latest_status == 'completed':
                        self.job_complete = True

                        if not self.complete_notice:
                            self._record_writer._inspector['messages'] = []
                            self.write_info('Cribl Search job complete.')

                    if latest_status == 'queued' and not self.queue_notice:
                        self._record_writer._inspector['messages'] = []
                        self.write_info('Waiting for queued Cribl Search job to start.')
                        self.queue_notice = True

                    if latest_status == 'running' and not self.running_notice:
                        self._record_writer._inspector['messages'] = []
                        self.write_info('Cribl Search job is running.')
                        self.running_notice = True
                
                # Terminate if the job has failed or been canceled
                if latest_status in ['failed', 'canceled']:
                    self._write_error(f"Cribl Search job {self.job_id} has status={status_obj}.")
                    break

                # Don't attempt to collect results until the job is running or complete
                if latest_status not in ['completed', 'running']:
                    print("Job not running or complete, waiting...", file=sys.stderr)
                    time.sleep(0.5)
                    continue

                # TODO: Do something when no results

                # TODO: Do something if the job fail

                collecting = True

                # Set the flush size to match the page size
                self.set_flush_size(self.api_limit)
                while collecting and not getattr(self, '_finalizing', False):
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

                    self.set_flush_size(self.api_limit)
                    for line in results_chunk.iter_lines():
                        if self._finalizing:
                            break
                        event = json.loads(line)

                        if 'totalEventCount' in event:
                            # Response metadata event handling
                            if self.debug:
                                # Emit messages as they are generated
                                if self.offset == 0:
                                    self.set_flush_size(1)
                                else:
                                    self.set_flush_size(self.api_limit)
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
                                    "host": "localhost",
                                    **event.get('items', {})
                                }
                            latest_status = event.get('job', {}).get('status', latest_status)
                            if 'totalEventCount' in event.keys():
                                self.total_event_count = event['totalEventCount']
                        else:
                            # Search result handling
                            if '_time' in event:
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
                    if self.debug:
                        print("Record count=%s" % self.offset, file=sys.stderr)
                    # Update the search metadata earliest/latest times (timeliner fix?)
                    self.update_earliest_latest(earliest_seen, latest_seen)
                    # Avoid overwhelming the API
                    time.sleep(0.1)
                    self.flush()

            if self.debug:
                for evt in self.event_log:
                    yield evt

    def prepare(self):
        user = self._metadata.searchinfo.username

        caps = self.service.users[user]['capabilities']

        if not 'goatsearch_user' in caps:
            self.write_error("You must have the 'goatsearch_user' capability to use this command.")
            return

        self.can_run = True

        self._record_writer._inspector['messages'] = []
        self.write_info("Getting environment settings.")
        self._get_environment()

        self._record_writer._inspector['messages'] = []
        self.write_info("Getting authentication token.")
        self._get_auth_token()
        self._record_writer._inspector['messages'] = []

        self.headers = {
            'Authorization': 'Bearer %s' % self.access_token,
            'Content-Type': 'application/json'
        }

        # TODO: Placeholder. This is hard-coded in the API documentation but the format suggests
        #       it could be a variable for a coming feature.
        self.search_context = 'default_search'
        

dispatch(goatsearch, sys.argv, sys.stdin, sys.stdout, __name__)
