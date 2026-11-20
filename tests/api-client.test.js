import test from 'node:test';
import assert from 'node:assert/strict';
import { api, setCsrf } from '../frontend/src/api.js';

const originalFetch = globalThis.fetch;

test.afterEach(() => {
    globalThis.fetch = originalFetch;
    setCsrf('');
});

test('refreshes an expired CSRF token and retries registration once', async () => {
    const calls = [];

    globalThis.fetch = async (url, options) => {
        calls.push({ url, options });

        if (url === '/api/session') {
            return new Response(JSON.stringify({ csrf_token: 'fresh-token', user: null }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        if (calls.filter((call) => call.url === '/api/register').length === 1) {
            return new Response(JSON.stringify({ error: 'Security check expired. Refresh and try again.' }), {
                status: 400,
                headers: { 'Content-Type': 'application/json' }
            });
        }

        return new Response(JSON.stringify({ message: 'Account request submitted.' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
        });
    };

    setCsrf('expired-token');
    const result = await api('/register', {
        method: 'POST',
        body: { matric_no: 'DEMO/2026/000001' }
    });

    assert.equal(result.message, 'Account request submitted.');
    assert.deepEqual(calls.map((call) => call.url), [
        '/api/register',
        '/api/session',
        '/api/register'
    ]);
    assert.equal(calls[0].options.headers['X-CSRFToken'], 'expired-token');
    assert.equal(calls[2].options.headers['X-CSRFToken'], 'fresh-token');
    assert.equal(calls[2].options.credentials, 'same-origin');
});

test('obtains a CSRF token before a state-changing request when none is cached', async () => {
    const calls = [];

    globalThis.fetch = async (url, options) => {
        calls.push({ url, options });
        if (url === '/api/session') {
            return new Response(JSON.stringify({ csrf_token: 'initial-token', user: null }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' }
            });
        }
        return new Response(JSON.stringify({ message: 'Request accepted.' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
        });
    };

    setCsrf('');
    const result = await api('/register', { method: 'POST', body: {} });

    assert.equal(result.message, 'Request accepted.');
    assert.deepEqual(calls.map((call) => call.url), ['/api/session', '/api/register']);
    assert.equal(calls[1].options.headers['X-CSRFToken'], 'initial-token');
});
