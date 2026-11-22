import test from 'node:test';
import assert from 'node:assert/strict';
import { api, fetchPrivateImage, setCsrf } from '../frontend/src/api.js';

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


test('loads a private student photograph with the authenticated same-origin session', async () => {
    let call;
    const expected = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
    globalThis.fetch = async (url, options) => {
        call = { url, options };
        return new Response(expected, {
            status: 200,
            headers: { 'Content-Type': 'image/jpeg' }
        });
    };

    const image = await fetchPrivateImage('/api/student/my-photo');
    assert.equal(call.url, '/api/student/my-photo');
    assert.equal(call.options.credentials, 'same-origin');
    assert.equal(call.options.cache, 'no-store');
    assert.equal(call.options.headers.Accept, 'image/jpeg, image/png, image/webp');
    assert.equal(image.type, 'image/jpeg');
    assert.deepEqual(new Uint8Array(await image.arrayBuffer()), expected);
});

test('rejects a private-photo response that is not an image', async () => {
    globalThis.fetch = async () => new Response(JSON.stringify({ error: 'Please sign in to continue.' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' }
    });

    await assert.rejects(
        fetchPrivateImage('/api/student/my-photo'),
        (error) => error.status === 401 && error.message === 'Please sign in to continue.'
    );
});

test('rejects photo URLs outside the authenticated application API', async () => {
    await assert.rejects(
        fetchPrivateImage('https://example.com/photo.jpg'),
        (error) => error.status === 0 && error.message === 'The profile photograph address is invalid.'
    );
});
