import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def temporary_directory():
	base_path = Path.cwd() / ".test-tmp"
	base_path.mkdir(exist_ok=True)
	path = base_path / uuid.uuid4().hex
	path.mkdir()
	try:
		yield str(path)
	finally:
		shutil.rmtree(path, ignore_errors=True)
