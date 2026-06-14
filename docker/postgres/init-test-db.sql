SELECT 'CREATE DATABASE masaar_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'masaar_test')\gexec
