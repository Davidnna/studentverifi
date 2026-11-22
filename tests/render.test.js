import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server.js';
import { AuthProvider, PublicShell, DashboardShell } from '../frontend/src/components.js';
import { Register } from '../frontend/src/pages.js';

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


test('registration initially displays only account identification', () => {
    const markup = renderShell(Register, '/register');
    assert.match(markup, /Claim your student account/);
    assert.match(markup, /Send verification code/);
    assert.doesNotMatch(markup, /STEP [123] OF 3|claim-progress|registration-steps|Choose your profile photograph|Activate my account|Six-digit verification code/);
});
