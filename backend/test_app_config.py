import os
import unittest


class DatabaseConfigTests(unittest.TestCase):
    def test_build_database_url_uses_runtime_values(self):
        os.environ["DB_USER"] = "medilink"
        os.environ["DB_PASSWORD"] = "secret@123"
        os.environ["DB_HOST"] = "localhost"
        os.environ["DB_PORT"] = "5432"
        os.environ["DB_NAME"] = "medilink"

        from database import build_database_url

        self.assertEqual(
            build_database_url(),
            "postgresql://medilink:secret%40123@localhost:5432/medilink",
        )

    def test_require_database_settings_raises_clear_error_for_missing_values(self):
        for key in ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]:
            os.environ.pop(key, None)

        from database import require_database_settings

        with self.assertRaises(RuntimeError):
            require_database_settings()


if __name__ == "__main__":
    unittest.main()
