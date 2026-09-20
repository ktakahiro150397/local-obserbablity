import contextlib
import io
import os
from pathlib import Path
import runpy
import socket
import tempfile
import unittest
from unittest.mock import patch


class SocketRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.socket=self.root/".local/state/ai-usage/socket/otlp.sock"
        self.socket.parent.mkdir(parents=True)

    def tearDown(self):self.temp.cleanup()

    def run_helper(self):
        with patch("pathlib.Path.home",return_value=self.root),patch("sys.argv",["prepare-socket.py"]),contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(Path(__file__).with_name("prepare-socket.py")),run_name="__main__")

    def test_regular_file_preserved(self):
        self.socket.write_text("data")
        with self.assertRaises(AssertionError):self.run_helper()
        self.assertEqual(self.socket.read_text(),"data")

    def test_active_socket_preserved(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.bind(str(self.socket));s.listen(1)
            with self.assertRaises(SystemExit) as e:self.run_helper()
            self.assertEqual(e.exception.code,3)
            self.assertTrue(self.socket.exists())

    def test_only_stale_socket_replaced(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:s.bind(str(self.socket))
        self.run_helper()
        self.assertFalse(self.socket.exists())


if __name__=="__main__":unittest.main()
