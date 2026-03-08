from tornado.testing import AsyncHTTPTestCase
from app.main import Application


class TestHealth(AsyncHTTPTestCase):
    def get_app(self):
        return Application()

    def test_health(self):
        response = self.fetch("/health")
        assert response.code == 200
