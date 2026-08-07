from django.test import TestCase
from django.urls import reverse


class DeliveryEndpointsTests(TestCase):
    def test_health_reports_database_available(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_openapi_schema_is_publicly_available(self):
        response = self.client.get(reverse("schema"))

        self.assertEqual(response.status_code, 200)
