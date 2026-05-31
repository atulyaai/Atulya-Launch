"""Quick plugin verification test."""
import sys
import json
sys.path.insert(0, '.')

from atulya_launch.web.api.plugins.cms_installer import CMS_MANIFEST
from atulya_launch.web.api.plugins.security_advisor import ALL_CHECKS
from atulya_launch.web.api.plugins.reseller import _load_plans, _load_branding
from atulya_launch.web.api.plugins.antivirus import _load_config as av_config

print("=== CMS Installer ===")
print("Apps in manifest:", len(CMS_MANIFEST))
for app in CMS_MANIFEST:
    print("  -", app["title"], "v" + app["version"])

print()
print("=== Security Advisor ===")
print("Checks defined:", len(ALL_CHECKS))
for check_fn in ALL_CHECKS:
    print("  -", check_fn.__name__)

print()
print("=== Reseller Plans ===")
plans = _load_plans()
print("Plans:", len(plans))
for p in plans:
    print("  -", p["name"], "($" + str(p["price_monthly"]) + "/mo)")

print()
print("=== Branding ===")
branding = _load_branding()
print("Company:", branding["company_name"])
print("Color:", branding["primary_color"])

print()
print("=== Antivirus ===")
av = av_config()
print("Enabled:", av["enabled"])
print("Scan uploads:", av["scan_uploads"])

print()
print("All plugin systems verified!")
