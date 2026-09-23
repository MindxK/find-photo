"""Fixed Tailscale Funnel routing; never silently replace a pinned hostname."""
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


def load_config(data):
    path = data / 'tunnel-config.json'
    if not path.exists():
        return {'provider':'cloudflare-quick'}
    config = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Tunnel configuration must be an object')
    if config.get('provider') == 'cloudflare-quick':
        return {'provider':'cloudflare-quick'}
    if config.get('provider') != 'tailscale':
        raise ValueError('Unknown tunnel provider; configuration must be corrected')
    if not isinstance(config.get('public_origin'), str):
        raise ValueError('A fixed HTTPS Tailscale machine URL is required')
    origin = config['public_origin'].rstrip('/')
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.netloc != parsed.hostname
            or parsed.path or parsed.query or parsed.fragment
            or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.ts\.net', parsed.hostname)):
        raise ValueError('A fixed HTTPS Tailscale machine URL is required')
    return {'provider':'tailscale','public_origin':origin}


def tailscale(*args):
    executable = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tailscale' / 'tailscale.exe'
    result = subprocess.run([str(executable), *args], capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=20, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError('Tailscale command failed; check Tailscale sign-in and Funnel permissions')
    return json.loads(result.stdout) if '--json' in args else result.stdout


def owns_route(config, origin, port):
    host = urlsplit(origin).hostname + ':443'
    web = config.get('Web', {})
    return (config.get('TCP', {}).get('443') == {'HTTPS':True}
            and web.get(host) == {'Handlers':{'/':{'Proxy':f'http://127.0.0.1:{port}'}}}
            and all(key == host or not key.endswith(':443') for key in web))


def ensure_tailscale(origin, port):
    state = tailscale('status','--json')
    if state.get('BackendState') != 'Running':
        raise RuntimeError('Tailscale is offline; open Tailscale and sign in')
    actual = 'https://' + state.get('Self',{}).get('DNSName','').rstrip('.')
    if actual != origin:
        raise RuntimeError('Tailscale device URL changed; keeping the configured URL until an administrator updates it')
    config = tailscale('funnel','status','--json')
    host = urlsplit(origin).hostname + ':443'
    if config.get('TCP',{}).get('443') and not owns_route(config,origin,port):
        raise RuntimeError('Tailscale port 443 belongs to another service; it was not changed')
    if not owns_route(config,origin,port) or not config.get('AllowFunnel',{}).get(host):
        tailscale('funnel','--bg','--https=443',f'http://127.0.0.1:{port}')
        config = tailscale('funnel','status','--json')
        if not owns_route(config,origin,port) or not config.get('AllowFunnel',{}).get(host):
            raise RuntimeError('Funnel did not publish the expected FindFace route')
    return origin


def stop_tailscale(origin, port):
    config = tailscale('funnel','status','--json')
    if owns_route(config,origin,port):
        tailscale('funnel','--https=443','off')
