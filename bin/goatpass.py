import json
import os
import re
import requests
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from splunklib.searchcommands import \
    dispatch, StreamingCommand, Configuration, Option, validators

@Configuration(local=True)
class goatpass(StreamingCommand):
    delete = Option(require=False, validate=None)

    def stream(self, events):
        # TODO: Make sure the _key, tenant, and password fields are there.

        storage_passwords = self.service.storage_passwords

        if self.delete:
            kvquery = {
                "_key": self.delete
            }

            collection = self.service.kvstore['goatsearch_env_kv']

            tenants = collection.data.query(query=kvquery)

            delete_str = '<<UNKNOWN_%sw>>' % self.delete

            for tenant in tenants:
                credential_name = '%s:%s' % (
                    tenant['tenant'],
                    tenant['clientId']
                )

                if credential_name in storage_passwords:
                    storage_passwords.delete(credential_name)
                    delete_str = '<<DELETED_%s>>' % self.delete

            for event in events:
                event['clientSecret'] = delete_str

                yield event

        else:
            for event in events:
                required_keys = set(['tenant', 'clientId', 'clientSecret'])

                if all(key in event for key in required_keys):
                    credential_name = '%s:%s' % (
                        event['tenant'],
                        event['clientId']
                    )

                    if credential_name in storage_passwords:
                        storage_passwords[credential_name].update(password=event['clientSecret'])
                    else:
                        storage_passwords.create(event['clientSecret'], event['clientId'], event['tenant'])

                    event['clientSecret'] = '<<HASHED>>'

                    confs = self.service.confs

                    for conf in confs.iter():
                        if conf.name == 'app':
                            app_config = conf
                            break

                    for stanza in app_config.iter():
                        if stanza.name == 'install':
                            stanza.update(is_configured=1)
                            break

                    app = self.service.apps['GoatSearch']
                    app.reload()
                else:
                    event['clientSecret'] = '<<MISSING_FIELDS>>'

                yield event
 
dispatch(goatpass, sys.argv, sys.stdin, sys.stdout, __name__)
