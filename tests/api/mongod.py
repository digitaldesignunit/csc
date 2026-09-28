"""
A throwaway ``mongod`` for route tests and local development (no Docker).

The binary is taken from ``$MONGOD_BIN``, then ``PATH``, then the default
Windows install location of MongoDB Community Server. Each instance gets a
free port and a temporary data directory that is deleted on stop.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Optional

from pymongo import MongoClient
from pymongo.errors import PyMongoError

_WINDOWS_GLOB = r'C:\Program Files\MongoDB\Server\*\bin\mongod.exe'


def _version_key(path: str):
    match = re.search(r'Server[\\/](\d+)\.(\d+)', path)
    return tuple(int(x) for x in match.groups()) if match else (0, 0)


def find_mongod() -> Optional[str]:
    explicit = os.getenv('MONGOD_BIN')
    if explicit and os.path.isfile(explicit):
        return explicit
    on_path = shutil.which('mongod')
    if on_path:
        return on_path
    installed = sorted(glob.glob(_WINDOWS_GLOB), key=_version_key)
    return installed[-1] if installed else None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ThrowawayMongod:
    def __init__(self, binary: str):
        self.binary = binary
        self.dbpath = tempfile.mkdtemp(prefix='csc-mongod-')
        self.port = _free_port()
        self.process: Optional[subprocess.Popen] = None

    @property
    def uri(self) -> str:
        return f'mongodb://127.0.0.1:{self.port}'

    def start(self, timeout_s: float = 30.0) -> 'ThrowawayMongod':
        args = [
            self.binary,
            '--dbpath', self.dbpath,
            '--port', str(self.port),
            '--bind_ip', '127.0.0.1',
            '--logpath', os.path.join(self.dbpath, 'mongod.log'),
            '--wiredTigerCacheSizeGB', '0.25',
        ]
        if os.name != 'nt':
            args.append('--nounixsocket')
        self.process = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f'mongod exited with code {self.process.returncode}; '
                    f'see {self.dbpath}/mongod.log'
                )
            try:
                with MongoClient(self.uri, serverSelectionTimeoutMS=500) as c:
                    c.admin.command('ping')
                return self
            except PyMongoError:
                time.sleep(0.2)
        self.stop()
        raise RuntimeError(f'mongod did not answer within {timeout_s} s')

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process = None
        shutil.rmtree(self.dbpath, ignore_errors=True)
