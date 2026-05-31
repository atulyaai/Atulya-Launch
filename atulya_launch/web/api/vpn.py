"""WireGuard VPN Management API."""

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from atulya_launch import utils
from atulya_launch.web.auth import get_current_user

router = APIRouter(prefix="/api/vpn", tags=["vpn"])

VPN_CONFIG_FILE = utils.CONFIG_DIR / "vpn.json"
WG_DIR = Path("/etc/wireguard")
WG_INTERFACE = "wg0"


def _load_vpn_config() -> dict:
    if VPN_CONFIG_FILE.exists():
        with open(VPN_CONFIG_FILE, "r") as f:
            return json.load(f) or {}
    return {}


def _save_vpn_config(data: dict):
    utils.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(VPN_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _wg_available() -> bool:
    return shutil.which("wg") is not None


def _get_server_keys() -> dict:
    private_key = ""
    public_key = ""
    result = utils.run_command(["wg", "genkey"], check=False)
    if result and result.returncode == 0:
        private_key = result.stdout.strip()
        result2 = subprocess.run(
            ["wg", "pubkey"],
            input=private_key,
            capture_output=True,
            text=True,
            check=False,
        )
        if result2.returncode == 0:
            public_key = result2.stdout.strip()
    return {"private_key": private_key, "public_key": public_key}


def _get_peer_config(public_key: str, endpoint: str, allowed_ips: str) -> dict:
    private = ""
    result = utils.run_command(["wg", "genkey"], check=False)
    if result and result.returncode == 0:
        private = result.stdout.strip()
    return {
        "private_key": private,
        "public_key": public_key,
        "endpoint": endpoint,
        "allowed_ips": allowed_ips,
    }


def _get_wg_status() -> dict:
    if not _wg_available():
        return {"installed": False}

    result = utils.run_command(["wg", "show"], check=False)
    if not result or result.returncode != 0:
        return {"installed": True, "running": False}

    lines = result.stdout.strip().split("\n")
    interface = {}
    peers = []
    current_peer = None

    for line in lines:
        line = line.strip()
        if line.startswith("interface:"):
            continue
        if line.startswith("private key:"):
            interface["private_key"] = line.split(":", 1)[1].strip()
        elif line.startswith("public key:"):
            interface["public_key"] = line.split(":", 1)[1].strip()
        elif line.startswith("listening port:"):
            interface["listening_port"] = line.split(":", 1)[1].strip()
        elif line.startswith("peer:"):
            if current_peer:
                peers.append(current_peer)
            current_peer = {"public_key": line.split(":", 1)[1].strip()}
        elif line.startswith("endpoint:") and current_peer:
            current_peer["endpoint"] = line.split(":", 1)[1].strip()
        elif line.startswith("allowed ips:") and current_peer:
            current_peer["allowed_ips"] = line.split(":", 1)[1].strip()
        elif line.startswith("latest handshake:") and current_peer:
            current_peer["latest_handshake"] = line.split(":", 1)[1].strip()
        elif line.startswith("transfer:") and current_peer:
            current_peer["transfer"] = line.split(":", 1)[1].strip()

    if current_peer:
        peers.append(current_peer)

    return {
        "installed": True,
        "running": True,
        "interface": interface,
        "peers": peers,
    }


class VPNInstall(BaseModel):
    port: int = 51820
    subnet: str = "10.0.0.0/24"
    dns: str = "1.1.1.1,1.0.0.1"


class PeerAdd(BaseModel):
    name: str
    allowed_ips: str = "10.0.0.2/32"
    endpoint: Optional[str] = None
    persistent_keepalive: int = 25


@router.get("/status")
def vpn_status(user: dict = Depends(get_current_user)):
    status = _get_wg_status()
    config = _load_vpn_config()
    status["config"] = config
    return status


@router.post("/install")
def install_vpn(body: VPNInstall, user: dict = Depends(get_current_user)):
    if not _wg_available():
        utils.run_command(["apt-get", "update", "-qq"], check=False)
        utils.run_command(["apt-get", "install", "-y", "-qq", "wireguard"], check=False)

    if not _wg_available():
        raise HTTPException(status_code=500, detail="Failed to install WireGuard")

    keys = _get_server_keys()
    if not keys["private_key"] or not keys["public_key"]:
        raise HTTPException(status_code=500, detail="Failed to generate keys")

    server_ip = "10.0.0.1"
    WG_DIR.mkdir(parents=True, exist_ok=True)

    config_content = f"""[Interface]
Address = {server_ip}/24
ListenPort = {body.port}
PrivateKey = {keys['private_key']}
PostUp = iptables -A FORWARD -i {WG_INTERFACE} -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i {WG_INTERFACE} -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

# Peers will be added below
"""
    config_path = WG_DIR / f"{WG_INTERFACE}.conf"
    with open(config_path, "w") as f:
        f.write(config_content)

    utils.run_command(["chmod", "600", str(config_path)], check=False)

    vpn_config = {
        "installed": True,
        "port": body.port,
        "subnet": body.subnet,
        "dns": body.dns,
        "server_public_key": keys["public_key"],
        "server_ip": server_ip,
        "installed_at": datetime.now().isoformat(),
    }
    _save_vpn_config(vpn_config)

    utils.run_command(["systemctl", "enable", f"wg-quick@{WG_INTERFACE}"], check=False)
    utils.run_command(["systemctl", "start", f"wg-quick@{WG_INTERFACE}"], check=False)

    return {"status": "installed", "vpn": vpn_config}


@router.get("/peers")
def list_peers(user: dict = Depends(get_current_user)):
    config = _load_vpn_config()
    peers = config.get("peers", [])
    status = _get_wg_status()
    running_peers = {p.get("public_key"): p for p in status.get("peers", [])}

    enriched = []
    for peer in peers:
        pubkey = peer.get("public_key")
        if pubkey in running_peers:
            peer.update(running_peers[pubkey])
        enriched.append(peer)

    return {"peers": enriched}


@router.post("/peers")
def add_peer(body: PeerAdd, user: dict = Depends(get_current_user)):
    config = _load_vpn_config()
    if not config.get("installed"):
        raise HTTPException(status_code=400, detail="VPN not installed")

    private_key = ""
    result = utils.run_command(["wg", "genkey"], check=False)
    if not result or result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to generate key")
    private_key = result.stdout.strip()

    result2 = subprocess.run(
        ["wg", "pubkey"],
        input=private_key,
        capture_output=True,
        text=True,
        check=False,
    )
    if result2.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to derive public key")
    public_key = result2.stdout.strip()

    next_ip = f"10.0.0.{len(config.get('peers', [])) + 2}/32"

    peer = {
        "name": body.name,
        "private_key": private_key,
        "public_key": public_key,
        "allowed_ips": body.allowed_ips or next_ip,
        "endpoint": body.endpoint,
        "persistent_keepalive": body.persistent_keepalive,
        "created_at": datetime.now().isoformat(),
    }

    wg_add_cmd = [
        "wg", "set", WG_INTERFACE,
        "peer", public_key,
        "allowed-ips", peer["allowed_ips"],
    ]
    if body.endpoint:
        wg_add_cmd.extend(["endpoint", body.endpoint])
    wg_add_cmd.extend(["persistent-keepalive", str(body.persistent_keepalive)])

    utils.run_command(wg_add_cmd, check=False)

    config.setdefault("peers", []).append(peer)
    _save_vpn_config(config)

    return {"status": "added", "peer": peer}


@router.delete("/peers/{peer_id}")
def delete_peer(peer_id: str, user: dict = Depends(get_current_user)):
    config = _load_vpn_config()
    peers = config.get("peers", [])
    found = None
    for p in peers:
        if p.get("public_key") == peer_id or p.get("name") == peer_id:
            found = p
            break
    if not found:
        raise HTTPException(status_code=404, detail="Peer not found")

    utils.run_command(["wg", "set", WG_INTERFACE, "peer", found["public_key"], "remove"], check=False)

    config["peers"] = [p for p in peers if p.get("public_key") != found["public_key"]]
    _save_vpn_config(config)
    return {"status": "deleted", "peer_id": peer_id}


@router.post("/peers/{peer_id}/config")
def get_peer_config(peer_id: str, user: dict = Depends(get_current_user)):
    config = _load_vpn_config()
    peers = config.get("peers", [])
    peer = None
    for p in peers:
        if p.get("public_key") == peer_id or p.get("name") == peer_id:
            peer = p
            break
    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found")

    server_pub = config.get("server_public_key", "")
    port = config.get("port", 51820)
    dns = config.get("dns", "1.1.1.1")
    server_ip = config.get("server_ip", "10.0.0.1")

    public_ip = ""
    result = utils.run_command(["curl", "-s", "ifconfig.me"], check=False)
    if result and result.returncode == 0:
        public_ip = result.stdout.strip()

    client_config = f"""[Interface]
PrivateKey = {peer['private_key']}
Address = {peer['allowed_ips'].split('/')[0]}/24
DNS = {dns}

[Peer]
PublicKey = {server_pub}
Endpoint = {public_ip}:{port}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = {peer.get('persistent_keepalive', 25)}
"""
    return PlainTextResponse(
        content=client_config,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{peer.get("name", "peer")}.conf"'},
    )


@router.get("/config")
def get_server_config(user: dict = Depends(get_current_user)):
    config = _load_vpn_config()
    conf_path = WG_DIR / f"{WG_INTERFACE}.conf"
    if conf_path.exists():
        content = conf_path.read_text()
        safe_content = content
        for peer in config.get("peers", []):
            if peer.get("private_key"):
                safe_content = safe_content.replace(peer["private_key"], "***")
        if config.get("server_public_key"):
            result = utils.run_command(["wg", "show", WG_INTERFACE, "private-key"], check=False)
        return {"config": safe_content}
    return {"config": None}
