let csrfToken = '';
let csrfRefreshPromise = null;

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function setCsrf(token) {
    csrfToken = typeof token === 'string' ? token : '';
}

export class ApiError extends Error {
    constructor(message, status, details = null) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.details = details;
    }
}

async function readJson(response) {
    return response.json().catch(() => ({}));
}

async function refreshCsrf() {
    if (csrfRefreshPromise) {
        return csrfRefreshPromise;
    }

    csrfRefreshPromise = (async () => {
        let response;
        try {
            response = await fetch('/api/session', {
                method: 'GET',
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
                cache: 'no-store'
            });
        } catch (error) {
            throw new ApiError('Your security session could not be refreshed. Check your connection and try again.', 0);
        }

        const data = await readJson(response);
        if (!response.ok || !data.csrf_token) {
            throw new ApiError(
                data.error || 'Your security session could not be refreshed. Reload the page and try again.',
                response.status
            );
        }

        setCsrf(data.csrf_token);
        return csrfToken;
    })().finally(() => {
        csrfRefreshPromise = null;
    });

    return csrfRefreshPromise;
}

function isCsrfFailure(response, data) {
    if (response.status !== 400 && response.status !== 403) {
        return false;
    }

    const message = String(data?.error || data?.description || '').toLowerCase();
    return message.includes('security check') ||
        message.includes('csrf') ||
        message.includes('token has expired') ||
        message.includes('token is missing');
}

export async function api(path, { method = 'GET', body, signal } = {}) {
    const requestMethod = String(method).toUpperCase();
    const requiresCsrf = UNSAFE_METHODS.has(requestMethod);

    if (requiresCsrf && !csrfToken) {
        await refreshCsrf();
    }

    const send = () => {
        const headers = { Accept: 'application/json' };
        if (requiresCsrf && csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }
        if (body !== undefined && !(body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }

        return fetch('/api' + path, {
            method: requestMethod,
            headers,
            credentials: 'same-origin',
            cache: 'no-store',
            body: body === undefined
                ? undefined
                : body instanceof FormData
                    ? body
                    : JSON.stringify(body),
            signal
        });
    };

    let response;
    try {
        response = await send();
    } catch (error) {
        if (error.name === 'AbortError') {
            throw error;
        }
        throw new ApiError('Unable to connect. Check your connection and retry.', 0);
    }

    let data = await readJson(response);

    // Flask-WTF rejects an expired or missing token before the endpoint runs.
    // Refresh it and retry once; server-side CSRF protection remains enabled.
    if (requiresCsrf && isCsrfFailure(response, data)) {
        await refreshCsrf();
        try {
            response = await send();
        } catch (error) {
            if (error.name === 'AbortError') {
                throw error;
            }
            throw new ApiError('Unable to connect. Check your connection and retry.', 0);
        }
        data = await readJson(response);
    }

    if (!response.ok) {
        throw new ApiError(
            data.error || `Request failed (${response.status}).`,
            response.status,
            data.details || data.duplicates
        );
    }

    if (data.csrf_token) {
        setCsrf(data.csrf_token);
    }
    if (path === '/logout') {
        setCsrf('');
    }

    return data;
}

export async function fetchPrivateImage(path, { signal } = {}) {
    if (typeof path !== 'string' || !path.startsWith('/api/') || path.startsWith('//')) {
        throw new ApiError('The profile photograph address is invalid.', 0);
    }

    let response;
    try {
        response = await fetch(path, {
            method: 'GET',
            headers: { Accept: 'image/jpeg, image/png, image/webp' },
            credentials: 'same-origin',
            cache: 'no-store',
            signal
        });
    } catch (error) {
        if (error.name === 'AbortError') {
            throw error;
        }
        throw new ApiError('The profile photograph could not be reached. Check your connection and retry.', 0);
    }

    if (!response.ok) {
        const data = await readJson(response);
        throw new ApiError(
            data.error || `The profile photograph could not be loaded (${response.status}).`,
            response.status
        );
    }

    const contentType = (response.headers.get('Content-Type') || '').split(';', 1)[0].trim().toLowerCase();
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(contentType)) {
        throw new ApiError('The photo service did not return a supported image.', response.status);
    }

    const image = await response.blob();
    if (!image.size) {
        throw new ApiError('The stored profile photograph is empty.', response.status);
    }
    return image;
}

export const compactDate = (value) => {
    if (!value) {
        return '—';
    }

    const date = new Date(value);
    return Number.isNaN(date.getTime())
        ? String(value)
        : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};
