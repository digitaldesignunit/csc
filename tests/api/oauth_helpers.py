"""Shared by the OAuth and MCP tests: the connector flow of Claude, step by
step, and calls of the MCP endpoint."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlsplit

import limiter as lim

CALLBACK = 'https://claude.ai/api/mcp/auth_callback'
RESOURCE = 'http://localhost/mcp'
JSON_RPC = {'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json'}


def reset_address_counters():
    """The per-address limits of /register, /authorize and /token count in
    the shared store; a test that connects many times starts clean."""
    lim.shared_limiter._storage.reset()


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return verifier, challenge


def register(api, redirect_uris=(CALLBACK,), name='Claude', **extra):
    return api.post('/register', json={
        'client_name': name, 'redirect_uris': list(redirect_uris),
        'token_endpoint_auth_method': 'none',
        'grant_types': ['authorization_code', 'refresh_token'],
        'response_types': ['code'], **extra})


def authorize(api, client_id, challenge, redirect_uri=CALLBACK, **extra):
    params = {'response_type': 'code', 'client_id': client_id,
              'redirect_uri': redirect_uri, 'code_challenge': challenge,
              'code_challenge_method': 'S256', 'state': 'st-1',
              'resource': RESOURCE, 'scope': 'read:catalog', **extra}
    params = {k: v for k, v in params.items() if v is not None}
    return api.get('/authorize', params=params, follow_redirects=False)


def request_id_of(response) -> str:
    assert response.status_code == 302, response.text
    location = response.headers['location']
    assert location.startswith('http://localhost:3000/oauth/consent?request='), location
    return parse_qs(urlsplit(location).query)['request'][0]


def code_of(redirect_to: str) -> str:
    return parse_qs(urlsplit(redirect_to).query)['code'][0]


def exchange(api, client_id, code, verifier, redirect_uri=CALLBACK):
    return api.post('/token', data={
        'grant_type': 'authorization_code', 'code': code,
        'redirect_uri': redirect_uri, 'client_id': client_id,
        'code_verifier': verifier})


def refresh(api, client_id, token):
    return api.post('/token', data={
        'grant_type': 'refresh_token', 'refresh_token': token,
        'client_id': client_id})


def connect(api, user_headers, redirect_uri=CALLBACK, name='Claude'):
    """The whole flow for an account that may allow: returns the tokens, the
    client id and the answer of /token."""
    client_id = register(api, [redirect_uri], name).json()['client_id']
    verifier, challenge = pkce()
    rid = request_id_of(authorize(api, client_id, challenge, redirect_uri))
    decision = api.post(f'/oauth/requests/{rid}/decision',
                        json={'allow': True}, headers=user_headers)
    assert decision.status_code == 200, decision.text
    code = code_of(decision.json()['redirect_to'])
    token = exchange(api, client_id, code, verifier, redirect_uri)
    assert token.status_code == 200, token.text
    body = token.json()
    return {'client_id': client_id, 'access': body['access_token'],
            'refresh': body['refresh_token'], 'body': body, 'code': code,
            'verifier': verifier, 'request_id': rid}


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


def mcp_post(api, token, method, params=None, headers=None, rpc_id=1):
    body = {'jsonrpc': '2.0', 'id': rpc_id, 'method': method}
    if params is not None:
        body['params'] = params
    return api.post('/mcp', json=body, headers={
        **JSON_RPC, **(bearer(token) if token else {}), **(headers or {})})


def tool_result(api, token, name, **arguments):
    """``(is_error, content)`` of a tool call; content is parsed JSON when the
    tool answered, else the error text."""
    response = mcp_post(api, token, 'tools/call',
                        {'name': name, 'arguments': arguments})
    assert response.status_code == 200, (response.status_code, response.text)
    result = response.json()['result']
    text = ''.join(part['text'] for part in result['content'])
    if result.get('isError'):
        return True, text
    return False, json.loads(text)


def tool(api, token, name, **arguments):
    is_error, content = tool_result(api, token, name, **arguments)
    assert not is_error, content
    return content


GH_CLIENT = 'csc-grasshopper'
GH_REDIRECT = 'http://127.0.0.1:54321/callback'


def gh_sign_in(api, user_headers, computer='WORKSTATION-7'):
    """The Grasshopper client's flow (fixed client, loopback redirect): returns
    the parts of the token answer."""
    verifier, challenge = pkce()
    response = api.get('/authorize', params={
        'response_type': 'code', 'client_id': GH_CLIENT, 'redirect_uri': GH_REDIRECT,
        'code_challenge': challenge, 'code_challenge_method': 'S256', 'state': 'gh',
        'scope': 'gh:client', 'computer': computer}, follow_redirects=False)
    rid = request_id_of(response)
    decision = api.post(f'/oauth/requests/{rid}/decision', json={'allow': True}, headers=user_headers)
    assert decision.status_code == 200, decision.text
    token = exchange(api, GH_CLIENT, code_of(decision.json()['redirect_to']), verifier, GH_REDIRECT)
    assert token.status_code == 200, token.text
    body = token.json()
    return {'access': body['access_token'], 'refresh': body['refresh_token'], 'body': body}
