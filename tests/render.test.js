import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server.js';
import { AuthProvider, PublicShell, DashboardShell } from '../frontend/src/components.js';

const h = React.createElement;

function renderShell(Shell, path) {
    return renderToStaticMarkup(h(StaticRouter, { location: path },
        h(AuthProvider, null, h(Shell))
    ));
}

test('public shell renders without an undefined element factory', () => {
    const markup = renderShell(PublicShell, '/');
    assert.match(markup, /public-header/);
    assert.match(markup, /public-main/);
    assert.match(markup, /page-transition/);
    assert.doesNotMatch(markup, /workspace-sidebar/);
});

test('workspace shell renders its navigation and page container', () => {
    const markup = renderShell(DashboardShell, '/student/account');
    assert.match(markup, /workspace-sidebar/);
    assert.match(markup, /workspace-main/);
    assert.match(markup, /page-transition/);
});
