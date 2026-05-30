"""Timezone configuration API."""

import json
import subprocess
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/settings/timezone", tags=["timezone"])


def _get_current_timezone() -> str:
    if utils.is_linux():
        result = utils.run_command(["timedatectl", "show", "--property=Timezone", "--value"], check=False)
        if result and result.returncode == 0:
            return result.stdout.strip()

        result = utils.run_command(["readlink", "/etc/localtime"], check=False)
        if result and result.returncode == 0:
            tz_path = result.stdout.strip()
            if "/zoneinfo/" in tz_path:
                return tz_path.split("/zoneinfo/")[-1]

    import time
    return "UTC"


def _list_timezones() -> list:
    tz_data = []
    zones_path = "/usr/share/zoneinfo/zone.tab"
    if utils.is_linux() and __import__("os").path.exists(zones_path):
        with open(zones_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    tz_data.append({
                        "country_code": parts[0],
                        "coordinates": parts[1],
                        "timezone": parts[2],
                    })
        return tz_data

    try:
        import importlib.resources
        tz_data_raw = importlib.resources.files("zoneinfo").joinpath("zone.tab").read_text()
        for line in tz_data_raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                tz_data.append({
                    "country_code": parts[0],
                    "coordinates": parts[1],
                    "timezone": parts[2],
                })
    except Exception:
        common_tzs = [
            "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
            "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Moscow",
            "Asia/Tokyo", "Asia/Shanghai", "Asia/Kolkata", "Asia/Dubai",
            "Australia/Sydney", "Pacific/Auckland", "America/Sao_Paulo",
            "Africa/Cairo", "Africa/Johannesburg",
        ]
        for tz in common_tzs:
            tz_data.append({"timezone": tz})

    return tz_data


class TimezoneSet(BaseModel):
    timezone: str


@router.get("")
def get_timezone(user: dict = Depends(get_current_user)):
    return {"timezone": _get_current_timezone()}


@router.put("")
def set_timezone(body: TimezoneSet, user: dict = Depends(get_current_user)):
    if not body.timezone:
        raise HTTPException(status_code=400, detail="Timezone is required")

    if utils.is_linux():
        result = utils.run_command(["timedatectl", "set-timezone", body.timezone], check=False)
        if result and result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to set timezone: {result.stderr}")
    else:
        raise HTTPException(status_code=400, detail="Timezone change is only supported on Linux")

    return {"status": "timezone_set", "timezone": body.timezone}


@router.get("/list")
def list_timezones(user: dict = Depends(get_current_user)):
    timezones = _list_timezones()
    return {"timezones": timezones, "current": _get_current_timezone()}
