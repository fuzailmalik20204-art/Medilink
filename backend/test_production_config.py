import os
import unittest

import database


class ProductionConfigTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "DATABASE_URL",
                "DB_USER",
                "DB_PASSWORD",
                "DB_HOST",
                "DB_PORT",
                "DB_NAME",
                "ALLOWED_ORIGINS",
            ]
        }

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_database_url_uses_sqlite_fallback_when_postgres_is_missing(self):
        for key in ["DATABASE_URL", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]:
            os.environ.pop(key, None)

        url = database.build_database_url()
        self.assertTrue(url.startswith("sqlite:///"), url)

    def test_database_url_normalizes_render_postgres_scheme(self):
        os.environ["DATABASE_URL"] = "postgres://user:password@host:5432/medilink"

        url = database.build_database_url()

        self.assertEqual(
            url,
            "postgresql://user:password@host:5432/medilink",
        )

    def test_allowed_origins_parses_csv_values(self):
        os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000, https://app.example.com, http://127.0.0.1:5500"
        origins = database.parse_allowed_origins()
        self.assertEqual(
            origins,
            [
                "http://localhost:3000",
                "https://app.example.com",
                "http://127.0.0.1:5500",
            ],
        )


if __name__ == "__main__":
    unittest.main()
