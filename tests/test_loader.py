import importlib
import os
import tempfile
import unittest
from pathlib import Path


class LoaderTests(unittest.TestCase):
    def test_load_uses_app_env_from_dotenv(self):
        from skuumate.settings import loader

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("APP_ENV=production\n", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            os.environ.pop("APP_ENV", None)
            os.environ.pop("DJANGO_SETTINGS_MODULE", None)

            try:
                importlib.reload(loader)
                loader.load()
            finally:
                os.chdir(old_cwd)
                os.environ.pop("APP_ENV", None)
                os.environ.pop("DJANGO_SETTINGS_MODULE", None)
                importlib.reload(loader)

        self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "skuumate.settings.production")


if __name__ == "__main__":
    unittest.main()
