from django.test import TestCase
from django.apps import apps
from maintenance.apps import MaintenanceConfig


class ProjectSetupSmokeTest(TestCase):
    def test_app_is_installed(self):
        """Verify that the maintenance application is properly registered in INSTALLED_APPS."""
        self.assertIn("maintenance", [app.name for app in apps.get_app_configs()])
        self.assertEqual(apps.get_app_config("maintenance").name, MaintenanceConfig.name)

    def test_smoke_pass(self):
        """Sanity check that the Django test runner is functional."""
        self.assertTrue(True)
