from motor.motor_tornado import MotorClient
from app.core.config import get_settings


def create_client() -> MotorClient:
    settings = get_settings()
    return MotorClient(settings.mongodb_uri)


def get_db(client: MotorClient):
    settings = get_settings()
    return client[settings.mongodb_dbname]
