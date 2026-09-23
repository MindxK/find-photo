import json
import pytest
import server_tunnel as tunnel

ORIGIN='https://findface.example.ts.net'
PORT=8765


def route():
    host='findface.example.ts.net:443'
    return {'TCP':{'443':{'HTTPS':True}}, 'Web':{host:{'Handlers':{'/':{'Proxy':'http://127.0.0.1:8765'}}}}, 'AllowFunnel':{host:True}}


def test_config_pins_url_and_rejects_unsafe_origins(tmp_path):
    assert tunnel.load_config(tmp_path) == {'provider':'cloudflare-quick'}
    for value in ('http://findface.example.ts.net','https://evil.example','https://user@findface.example.ts.net','https://findface.example.ts.net:443','https://findface.example.ts.net/x'):
        (tmp_path/'tunnel-config.json').write_text(json.dumps({'provider':'tailscale','public_origin':value}))
        with pytest.raises(ValueError): tunnel.load_config(tmp_path)
    (tmp_path/'tunnel-config.json').write_text(json.dumps({'provider':'tailscale','public_origin':ORIGIN}))
    assert tunnel.load_config(tmp_path)['public_origin'] == ORIGIN


def test_existing_route_reused_after_restart(monkeypatch):
    calls=[]
    def cli(*args):
        calls.append(args)
        return {'BackendState':'Running','Self':{'DNSName':'findface.example.ts.net.'}} if args[0]=='status' else route()
    monkeypatch.setattr(tunnel,'tailscale',cli)
    assert tunnel.ensure_tailscale(ORIGIN,PORT) == ORIGIN
    assert tunnel.ensure_tailscale(ORIGIN,PORT) == ORIGIN
    assert all('--bg' not in args for args in calls)


def test_stopped_route_is_recreated_on_same_hostname(monkeypatch):
    configured=False
    calls=[]
    def cli(*args):
        nonlocal configured
        calls.append(args)
        if args[0]=='status': return {'BackendState':'Running','Self':{'DNSName':'findface.example.ts.net.'}}
        if args[:2]==('funnel','status'): return route() if configured else {}
        if '--bg' in args: configured=True
        elif 'off' in args: configured=False
        return ''
    monkeypatch.setattr(tunnel,'tailscale',cli)
    assert tunnel.ensure_tailscale(ORIGIN,PORT)==ORIGIN
    tunnel.stop_tailscale(ORIGIN,PORT)
    assert not configured
    assert tunnel.ensure_tailscale(ORIGIN,PORT)==ORIGIN
    assert calls.count(('funnel','--bg','--https=443','http://127.0.0.1:8765'))==2


def test_changed_device_name_never_falls_back_to_random_url(monkeypatch):
    calls=[]
    def cli(*args):
        calls.append(args)
        return {'BackendState':'Running','Self':{'DNSName':'another.example.ts.net.'}}
    monkeypatch.setattr(tunnel,'tailscale',cli)
    with pytest.raises(RuntimeError,match='URL changed'): tunnel.ensure_tailscale(ORIGIN,PORT)
    assert calls==[('status','--json')]


def test_other_services_are_never_overwritten_or_stopped(monkeypatch):
    other=route(); other['Web']['findface.example.ts.net:443']['Handlers']['/']['Proxy']='http://127.0.0.1:9999'
    calls=[]
    def cli(*args):
        calls.append(args)
        return {'BackendState':'Running','Self':{'DNSName':'findface.example.ts.net.'}} if args[0]=='status' else other
    monkeypatch.setattr(tunnel,'tailscale',cli)
    with pytest.raises(RuntimeError,match='another service'): tunnel.ensure_tailscale(ORIGIN,PORT)
    tunnel.stop_tailscale(ORIGIN,PORT)
    assert all('--bg' not in args and 'off' not in args for args in calls)
