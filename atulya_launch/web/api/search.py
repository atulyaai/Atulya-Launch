"""Global search API."""

import json
from fastapi import APIRouter, Depends, Query

from atulya_launch import core, utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def global_search(q: str = Query("", min_length=1), user: dict = Depends(get_current_user)):
    results = []
    q_lower = q.lower()

    # Search sites
    try:
        sites = core.site_list()
        for site in sites if isinstance(sites, dict) else {}:
            s = sites[site] if isinstance(sites, dict) else site
            domain = s.get("domain", site) if isinstance(s, dict) else str(site)
            if q_lower in domain.lower():
                results.append({"type": "site", "title": domain, "section": "websites"})
    except Exception:
        pass

    # Search databases
    try:
        dbs = core.db_list()
        for db_name in dbs if isinstance(dbs, dict) else {}:
            if q_lower in db_name.lower():
                results.append({"type": "database", "title": db_name, "section": "databases"})
    except Exception:
        pass

    # Search DNS zones
    try:
        dns_file = utils.CONFIG_DIR / "dns" / "zones.json"
        if dns_file.exists():
            zones = json.loads(dns_file.read_text())
            for zone_name in zones:
                if q_lower in zone_name.lower():
                    results.append({"type": "dns_zone", "title": zone_name, "section": "dns"})
    except Exception:
        pass

    # Search email accounts
    try:
        email_file = utils.CONFIG_DIR / "email.json"
        if email_file.exists():
            email_data = json.loads(email_file.read_text())
            for email in email_data.get("accounts", {}):
                if q_lower in email.lower():
                    results.append({"type": "email", "title": email, "section": "email"})
    except Exception:
        pass

    # Search subdomains
    try:
        sub_file = utils.CONFIG_DIR / "subdomains.json"
        if sub_file.exists():
            subs = json.loads(sub_file.read_text())
            for sid, sub in subs.items():
                full = f"{sub.get('subdomain','')}.{sub.get('domain','')}"
                if q_lower in full.lower():
                    results.append({"type": "subdomain", "title": full, "section": "subdomains"})
    except Exception:
        pass

    # Search files (limited)
    try:
        for root_dir in ["/var/www", "/home"]:
            import os
            for dirpath, dirnames, filenames in os.walk(root_dir):
                for fn in filenames:
                    if q_lower in fn.lower():
                        results.append({"type": "file", "title": os.path.join(dirpath, fn), "section": "files"})
                        if len(results) > 50:
                            break
                if len(results) > 50:
                    break
    except Exception:
        pass

    return {"results": results[:50], "total": len(results)}
