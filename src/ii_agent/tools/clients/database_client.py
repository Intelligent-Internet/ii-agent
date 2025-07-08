from abc import ABC, abstractmethod
import os
import requests

from dotenv import load_dotenv

from ii_agent.core.storage.models.settings import Settings

load_dotenv()


class DatabaseClient(ABC):
    @abstractmethod
    def get_database_connection(self):
        pass


class PostgresDatabaseClient(DatabaseClient):
    def __init__(self, setting: Settings):
        self.setting = setting
        self.neon_db_api_key = (
            setting.third_party_integration_config.neon_db_api_key.get_secret_value()
            if setting.third_party_integration_config.neon_db_api_key
            else None
        )

    def get_all_postgres_databases(self) -> list[str]:
        """
        Get all Postgres databases from Neon
        Returns a list of database IDs
        """
        if not self.neon_db_api_key:
            raise ValueError("NEON_API_KEY environment variable not set")
        headers = {
            "Authorization": f"Bearer {self.neon_db_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response = requests.get(
                "https://console.neon.tech/api/v2/projects?limit=10", headers=headers
            )
            projects = response.json()["projects"]
            return [project["id"] for project in projects]
        except requests.RequestException as e:
            raise Exception(f"Network error getting Neon databases: {str(e)}")

    def delete_postgres_database(self, database_id: str):
        """
        Delete a Postgres database from Neon
        """
        if not self.neon_db_api_key:
            raise ValueError("NEON_API_KEY environment variable not set")
        headers = {
            "Authorization": f"Bearer {self.neon_db_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response = requests.delete(
                f"https://console.neon.tech/api/v2/projects/{database_id}",
                headers=headers,
            )
            if response.status_code == 200:
                print(f"Deleted Neon database: {database_id}")
                return True
            else:
                raise Exception(
                    f"Failed to delete Neon database: {response.status_code} - {response.text}"
                )
        except requests.RequestException as e:
            raise Exception(f"Network error deleting Neon database: {str(e)}")

    def free_up_database_resources(self):
        """
        Free up database resources from Neon
        """
        if not self.neon_db_api_key:
            raise ValueError("NEON_API_KEY environment variable not set")
        while len(self.get_all_postgres_databases()) >= 10:
            self.delete_postgres_database(self.get_all_postgres_databases()[0])

    def create_postgresql(self) -> str:
        """
        Create PostgreSQL database using Neon
        Returns connection string
        """
        if not self.neon_db_api_key:
            raise ValueError("NEON_API_KEY environment variable not set")

        headers = {
            "Authorization": f"Bearer {self.neon_db_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "project": {
                "pg_version": 17,
            }
        }

        try:
            response = requests.post(
                "https://console.neon.tech/api/v2/projects",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 201:
                project_data = response.json()
                connection_uris = project_data.get("connection_uris", [])
                if connection_uris:
                    return connection_uris[0]["connection_uri"]
                raise Exception("No endpoints found in project response")
            else:
                raise Exception(
                    f"Failed to create Neon project: {response.status_code} - {response.text}"
                )
        except requests.RequestException as e:
            raise Exception(f"Network error creating Neon database: {str(e)}")

    def get_database_connection(self):
        self.free_up_database_resources()
        return self.create_postgresql()


class RedisDatabaseClient(DatabaseClient):
    def __init__(self, setting: Settings):
        pass

    def get_database_connection(self):
        return os.getenv("REDIS_URL")


class MySQLDatabaseClient(DatabaseClient):
    def __init__(self, setting: Settings):
        pass

    def get_database_connection(self):
        return os.getenv("MYSQL_URL")


def get_database_client(database_type: str, setting: Settings) -> DatabaseClient:
    if database_type == "postgres":
        return PostgresDatabaseClient(setting)
    elif database_type == "redis":
        return RedisDatabaseClient(setting)
    elif database_type == "mysql":
        return MySQLDatabaseClient(setting)
    else:
        raise ValueError(f"Invalid database type: {database_type}")


if __name__ == "__main__":
    database_client = get_database_client("postgres")
    print(database_client.get_database_connection())
    database_client = get_database_client("redis")
    print(database_client.get_database_connection())
    database_client = get_database_client("mysql")
    print(database_client.get_database_connection())
