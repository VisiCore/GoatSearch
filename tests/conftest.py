"""Minimal Splunk stubs for testing GoatSearch outside Splunk."""
import os
import sys
import time
from pathlib import Path

import pytest

# Add GoatSearch source to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))


class MockPassword:
    """Stub for password object returned by storage_passwords.list()."""

    def __init__(self, name, secret):
        self.name = name
        self._secret = secret

    def __getitem__(self, key):
        if key == "clear_password":
            return self._secret
        raise KeyError(key)


class MockPasswordCollection:
    """Stub for storage_passwords collection."""

    def __init__(self, passwords_dict):
        self._passwords = {
            name: MockPassword(name, secret) for name, secret in passwords_dict.items()
        }

    def list(self):
        return list(self._passwords.values())


class MockKVStoreData:
    """Stub for kvstore query results."""

    def __init__(self, data):
        self._data = data

    def query(self, query=None):
        return self._data


class MockKVStoreCollection:
    """Stub for kvstore collection access."""

    def __init__(self, data):
        self.data = MockKVStoreData(data)


class MockKVStore:
    """Stub for kvstore access by collection name."""

    def __init__(self, data_by_collection):
        self._data = data_by_collection

    def __getitem__(self, collection_name):
        if collection_name not in self._data:
            self._data[collection_name] = []
        return MockKVStoreCollection(self._data[collection_name])


class MockUser:
    """Stub for user object."""

    def __init__(self, capabilities):
        self._capabilities = capabilities

    def __getitem__(self, key):
        if key == "capabilities":
            return self._capabilities
        raise KeyError(key)


class MockUsersCollection:
    """Stub for users collection."""

    def __init__(self, user_capabilities):
        self._user = MockUser(user_capabilities)

    def __getitem__(self, username):
        return self._user


class MockService:
    """Stub Splunk service with credentials from environment."""

    def __init__(self, passwords_dict=None, kvstore_data=None, user_capabilities=None):
        self.storage_passwords = MockPasswordCollection(passwords_dict or {})
        self.kvstore = MockKVStore(kvstore_data or {})
        self.users = MockUsersCollection(user_capabilities or [])


@pytest.fixture(scope="session")
def live_credentials():
    """Load credentials from environment. Skip if not set."""
    creds = {
        "client_id": os.environ.get("CRIBL_CLIENT_ID", ""),
        "client_secret": os.environ.get("CRIBL_CLIENT_SECRET", ""),
        "tenant": os.environ.get("CRIBL_TENANT", ""),
        "workspace": os.environ.get("CRIBL_WORKSPACE", "main"),
    }
    if not all([creds["client_id"], creds["client_secret"], creds["tenant"]]):
        pytest.skip("Cribl credentials not configured")
    return creds


@pytest.fixture
def goatsearch_cmd(live_credentials):
    """Create goatsearch command configured for live API."""
    from goatsearch import goatsearch

    # Setup mock Splunk service with credentials
    password_key = f"{live_credentials['tenant']}:{live_credentials['client_id']}:"
    mock_service = MockService(
        passwords_dict={password_key: live_credentials["client_secret"]},
        kvstore_data={
            "goatsearch_env_kv": [
                {
                    "clientId": live_credentials["client_id"],
                    "tenant": live_credentials["tenant"],
                    "workspace": live_credentials["workspace"],
                    "default": 1,
                }
            ]
        },
        user_capabilities=["goatsearch_user"],
    )

    cmd = goatsearch()
    cmd._service = mock_service

    # Mock metadata
    cmd._metadata = type("M", (), {
        "searchinfo": type("S", (), {
            "earliest_time": "0",
            "latest_time": str(int(time.time())),
            "username": "admin",
        })()
    })()

    # Mock record writer
    cmd._record_writer = type("W", (), {
        "_inspector": {"messages": []},
        "messages": [],
        "flush": lambda s, finished=False: None,
        "write_message": lambda s, level, msg, *args: None,
    })()

    # Set command defaults
    cmd.tenant = None
    cmd.workspace = None
    cmd.sample = None
    cmd.page = 1000
    cmd.debug = False
    cmd.earliest = "-24h"
    cmd.latest = "now"
    cmd.sid = None
    cmd.retry = 3

    return cmd
