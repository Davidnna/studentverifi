import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { h, AuthProvider, AppShell, Protected, PageErrorBoundary } from './components.js';
import {
    Home,
    InfoPage,
    Login,
    Register,
    Dashboard,
    Students,
    StudentForm,
    StudentDetail,
    StudentImport,
    Verify,
    Requests,
    AdminAudit,
    StudentAccount,
    Password,
    Cleanup,
    Missing,
    PublicCredential,
    VerifierAccept,
    VerifierManagement,
    VerifierActivity
} from './pages.js';
import './style.css';

const route = (path, element) => h(Route, { key: path, path, element });
const info = (page) => route(page, h(InfoPage, { page: '/' + page }));

function ShellWithRecovery() {
    const location = useLocation();
    return h(PageErrorBoundary, { resetKey: location.pathname, fallbackTo: '/' }, h(AppShell));
}

function App() {
    return h(BrowserRouter, null,
        h(AuthProvider, null,
            h(Routes, null,
                h(Route, { path: '/', element: h(ShellWithRecovery) },
                    route('', h(Home)),
                    info('how-it-works'),
                    info('about'),
                    info('faq'),
                    info('privacy'),
                    info('contact'),
                    route('login', h(Login)),
                    route('register', h(Register)),
                    route('credential', h(PublicCredential)),
                    route('credential/:token', h(PublicCredential)),
                    route('verifier/accept', h(VerifierAccept)),
                    h(Route, { element: h(Protected, { role: 'admin' }) },
                        route('dashboard', h(Dashboard)),
                        route('students', h(Students)),
                        route('students/new', h(StudentForm)),
                        route('students/import', h(StudentImport)),
                        route('students/:id', h(StudentDetail)),
                        route('students/demo-cleanup', h(Cleanup)),
                        route('verifiers', h(VerifierManagement)),
                        route('registration-requests', h(Requests)),
                        route('logs', h(Navigate, { to: '/verify', replace: true })),
                        route('admin-audit', h(AdminAudit))
                    ),
                    h(Route, { element: h(Protected, { roles: ['admin', 'verifier'] }) },
                        route('verify', h(Verify))
                    ),
                    h(Route, { element: h(Protected, { role: 'verifier' }) },
                        route('verifier/dashboard', h(Verify)),
                        route('verifier/activity', h(VerifierActivity))
                    ),
                    h(Route, { element: h(Protected, { role: 'student' }) },
                        route('student/account', h(StudentAccount))
                    ),
                    h(Route, { element: h(Protected) },
                        route('account/password', h(Password))
                    ),
                    route('*', h(Missing))
                )
            )
        )
    );
}

createRoot(document.getElementById('root')).render(h(App));
