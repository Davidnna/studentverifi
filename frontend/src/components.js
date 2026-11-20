import React, { createContext, useContext, useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api, setCsrf } from './api.js';

export const h = React.createElement;
const AuthContext = createContext(null);

const iconPaths = {
    overview: ['M3 3h8v8H3z', 'M13 3h8v5h-8z', 'M13 10h8v11h-8z', 'M3 13h8v8H3z'],
    students: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8', 'M20 8v6', 'M23 11h-6'],
    verify: ['M12 3 4 6v5c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V6z', 'm8.5 12 2.2 2.2 4.8-5'],
    requests: ['M8 6h13', 'M8 12h13', 'M8 18h13', 'M3 6h.01', 'M3 12h.01', 'M3 18h.01'],
    history: ['M3 12a9 9 0 1 0 2.6-6.4L3 8', 'M3 3v5h5', 'M12 7v5l3 2'],
    audit: ['M4 4h16v16H4z', 'M8 8h8', 'M8 12h8', 'M8 16h5'],
    shield: ['M12 3 4 6v5c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V6z', 'm8.5 12 2.2 2.2 4.8-5'],
    arrow: ['M5 12h14', 'm13 6 6 6-6 6'],
    menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
    close: ['m6 6 12 12', 'M18 6 6 18'],
    logout: ['M10 17l5-5-5-5', 'M15 12H3', 'M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7'],
    home: ['m3 10 9-7 9 7', 'M5 9v12h14V9', 'M9 21v-7h6v7'],
    help: ['M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3', 'M12 17h.01', 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20'],
    plus: ['M12 5v14', 'M5 12h14'],
    file: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6', 'M8 13h8', 'M8 17h8'],
    user: ['M20 21a8 8 0 0 0-16 0', 'M12 13a4 4 0 1 0 0-8 4 4 0 0 0 0 8'],
    lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 1 1 8 0v4', 'M12 15v2'],
    book: ['M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22z', 'M4 5.5v16.5', 'M8 7h8', 'M8 11h8'],
    search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16', 'm17 17 4 4'],
    check: ['m5 12 4 4L19 6'],
    settings: ['M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8', 'M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.7 2.9-.2-.1a1.7 1.7 0 0 0-1.8.1l-.2.1h-3.4l-.1-.2a1.7 1.7 0 0 0-1.6-1l-.2.1-1.7-2.9.1-.2a1.7 1.7 0 0 0 0-1.8l-.1-.2V10l.2-.1a1.7 1.7 0 0 0 1-1.6l-.1-.2 2.9-1.7.2.1a1.7 1.7 0 0 0 1.8 0l.2-.1 2.9 1.7-.1.2a1.7 1.7 0 0 0 .1 1.8l.1.2v3.4z']
};

export function Icon({ name, size = 18 }) {
    const paths = iconPaths[name] || iconPaths.book;
    return h('svg', {
        width: size,
        height: size,
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        strokeWidth: 1.8,
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        'aria-hidden': 'true',
        focusable: 'false'
    }, ...paths.map((d, index) => h('path', { key: index, d })));
}

export function useAuth() {
    return useContext(AuthContext);
}

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [toast, setToast] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        const controller = new AbortController();
        api('/session', { signal: controller.signal })
            .then((data) => {
                setUser(data.user);
                setCsrf(data.csrf_token);
                setError('');
            })
            .catch((requestError) => {
                if (requestError.name !== 'AbortError') {
                    setError(requestError.message);
                }
            })
            .finally(() => {
                if (!controller.signal.aborted) {
                    setLoading(false);
                }
            });

        return () => controller.abort();
    }, []);

    const value = {
        user,
        loading,
        error,
        setUser,
        inform: (message, type = 'success') => setToast({ message, type }),
        dismiss: () => setToast(null),
        login: async (username, password) => {
            const data = await api('/login', {
                method: 'POST',
                body: { username, password }
            });
            setCsrf(data.csrf_token);
            setUser(data.user);
            return data.user;
        },
        logout: async () => {
            await api('/logout', { method: 'POST' });
            setCsrf('');
            setUser(null);
        }
    };

    return h(AuthContext.Provider, { value }, children,
        toast && h('div', {
            className: 'toast toast-' + toast.type,
            role: toast.type === 'error' ? 'alert' : 'status',
            'aria-live': toast.type === 'error' ? 'assertive' : 'polite'
        },
            h('p', null, toast.message),
            h('button', {
                type: 'button',
                className: 'icon-button',
                onClick: () => setToast(null),
                'aria-label': 'Dismiss notification'
            }, '×')
        )
    );
}

export function Button({ children, className = '', variant = 'primary', busy = false, type = 'button', ...props }) {
    return h('button', {
        type,
        className: 'button button-' + variant + ' ' + className,
        disabled: busy || props.disabled,
        'aria-busy': busy || undefined,
        ...props
    },
        busy ? h('span', { className: 'spinner', 'aria-hidden': 'true' }) : null,
        children
    );
}

export function Panel({ children, className = '', ...props }) {
    return h('section', { className: 'panel ' + className, ...props }, children);
}

export function TitleBlock({ eyebrow, title, description, actions }) {
    return h('div', { className: 'page-title' },
        h('div', { className: 'page-title-copy' },
            eyebrow && h('p', { className: 'eyebrow' }, eyebrow),
            h('h1', null, title),
            description && h('p', { className: 'lead' }, description)
        ),
        actions && h('div', { className: 'actions page-title-actions' }, actions)
    );
}

export function Pill({ status }) {
    const normalized = String(status || 'Unknown').toLowerCase();
    const theme = ['valid', 'active', 'approved', 'success'].includes(normalized)
        ? 'good'
        : ['invalid', 'inactive', 'rejected', 'revoked', 'error'].includes(normalized)
            ? 'bad'
            : 'neutral';
    return h('span', { className: 'pill pill-' + theme }, String(status || 'Unknown'));
}

export function Field({ label, name, hint, error, select, choices, textarea, ...props }) {
    const id = props.id || name;
    const helpId = hint || error ? id + '-help' : undefined;
    const base = {
        id,
        name,
        'aria-describedby': helpId,
        'aria-invalid': Boolean(error),
        ...props
    };
    let control;

    if (select) {
        control = h('select', base,
            h('option', { value: '' }, 'Choose an option'),
            ...(choices || []).map((choice) => h('option', {
                key: typeof choice === 'string' ? choice : choice.value,
                value: typeof choice === 'string' ? choice : choice.value
            }, typeof choice === 'string' ? choice : choice.label))
        );
    } else if (textarea) {
        control = h('textarea', base);
    } else {
        control = h('input', base);
    }

    return h('div', { className: 'field' },
        h('label', { htmlFor: id },
            label,
            props.required && h('span', { className: 'required-mark', 'aria-hidden': 'true' }, ' *')
        ),
        control,
        (hint || error) && h('small', {
            id: helpId,
            className: error ? 'field-error' : 'hint'
        }, error || hint)
    );
}

export function Problem({ message }) {
    return message ? h('div', { className: 'alert alert-error', role: 'alert' }, message) : null;
}

export function Empty({ title = 'Nothing here yet', text = 'Try a different search or come back later.' }) {
    return h('div', { className: 'empty' },
        h('span', { className: 'empty-icon', 'aria-hidden': 'true' }, h(Icon, { name: 'file', size: 24 })),
        h('h3', null, title),
        h('p', null, text)
    );
}

export function Spinner({ label = 'Loading…' }) {
    return h('div', { className: 'loading', role: 'status' },
        h('span', { className: 'spinner', 'aria-hidden': 'true' }),
        label
    );
}

export class PageErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError() {
        return { hasError: true };
    }

    componentDidCatch(error, info) {
        console.error('StudentVerifi page rendering failed.', error, info);
    }

    render() {
        if (this.state.hasError) {
            return h('section', { className: 'panel page-error-boundary', role: 'alert' },
                h('p', { className: 'eyebrow' }, 'DISPLAY ERROR'),
                h('h1', null, 'This page could not be displayed'),
                h('p', null, 'An unexpected display error occurred. Check the relevant activity history before repeating any action that may have been submitted.'),
                h('div', { className: 'actions' },
                    h(Link, { to: this.props.fallbackTo || '/', className: 'button button-primary' }, 'Return to overview')
                )
            );
        }

        return this.props.children;
    }
}

export function ConfirmAction({ title, text, action, dangerous = false, children, busy = false }) {
    const [open, setOpen] = useState(false);
    const triggerRef = React.useRef(null);
    const cancelRef = React.useRef(null);
    const dialogRef = React.useRef(null);

    function close() {
        setOpen(false);
        triggerRef.current?.focus();
    }

    useEffect(() => {
        if (!open) return undefined;
        cancelRef.current?.focus();

        const onKey = (event) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                close();
                return;
            }
            if (event.key === 'Tab' && dialogRef.current) {
                const controls = [...dialogRef.current.querySelectorAll(
                    'button:not(:disabled),a[href],input:not(:disabled)'
                )];
                if (!controls.length) return;
                if (event.shiftKey && document.activeElement === controls[0]) {
                    event.preventDefault();
                    controls[controls.length - 1].focus();
                } else if (!event.shiftKey && document.activeElement === controls[controls.length - 1]) {
                    event.preventDefault();
                    controls[0].focus();
                }
            }
        };

        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open]);

    return h(React.Fragment, null,
        h('button', {
            type: 'button',
            ref: triggerRef,
            className: 'button button-' + (dangerous ? 'danger' : 'outline'),
            onClick: () => setOpen(true),
            disabled: busy
        }, children),
        open && h('div', { className: 'modal-backdrop', role: 'presentation' },
            h('div', {
                ref: dialogRef,
                role: 'dialog',
                'aria-modal': 'true',
                'aria-labelledby': 'confirm-action-title',
                'aria-describedby': 'confirm-action-text',
                className: 'dialog'
            },
                h('p', { className: 'eyebrow' }, 'Please confirm'),
                h('h2', { id: 'confirm-action-title' }, title),
                h('p', { id: 'confirm-action-text' }, text),
                h('div', { className: 'actions' },
                    h('button', {
                        type: 'button',
                        ref: cancelRef,
                        className: 'button button-outline',
                        onClick: close
                    }, 'Cancel'),
                    h(Button, {
                        variant: dangerous ? 'danger' : 'primary',
                        busy,
                        onClick: async () => {
                            try {
                                await action();
                                close();
                            } catch (error) {
                                // The owning page displays the action error.
                            }
                        }
                    }, 'Confirm')
                )
            )
        )
    );
}

const publicLinks = [
    ['/', 'Home'],
    ['/how-it-works', 'How it works'],
    ['/about', 'About'],
    ['/faq', 'Help centre']
];

const adminGroups = [
    {
        label: 'Workspace',
        links: [
            ['/dashboard', 'Overview', 'overview'],
            ['/students', 'Student directory', 'students'],
            ['/students/new', 'Add student', 'plus'],
            ['/students/import', 'Import records', 'file']
        ]
    },
    {
        label: 'Verification',
        links: [
            ['/verify', 'Verification centre', 'verify'],
            ['/registration-requests', 'Account requests', 'requests']
        ]
    },
    {
        label: 'Administration',
        links: [
            ['/admin-audit', 'Admin activity', 'audit'],
            ['/students/demo-cleanup', 'Test data', 'settings'],
            ['/account/password', 'Account security', 'shield']
        ]
    }
];

const studentGroups = [
    {
        label: 'Student space',
        links: [
            ['/student/account', 'My student card', 'user'],
            ['/account/password', 'Account security', 'shield']
        ]
    }
];

const routeTitles = {
    '/dashboard': 'Overview',
    '/students': 'Student directory',
    '/students/new': 'Add student',
    '/students/import': 'Import student records',
    '/verify': 'Verification centre',
    '/registration-requests': 'Account requests',
    '/admin-audit': 'Administrative activity',
    '/account/password': 'Account security',
    '/student/account': 'My student card',
    '/students/demo-cleanup': 'Test data maintenance'
};

function Brand({ light = false }) {
    return h(Link, {
        to: '/',
        className: 'brand' + (light ? ' brand-light' : ''),
        'aria-label': 'StudentVerifi home'
    }, h('img', {
        src: '/logo.svg',
        alt: 'StudentVerifi',
        width: 176,
        height: 40
    }));
}

function PublicShell() {
    const { user, loading, error } = useAuth();
    const [menuOpen, setMenuOpen] = useState(false);
    const location = useLocation();

    useEffect(() => {
        setMenuOpen(false);
        document.getElementById('public-main')?.focus();
        window.scrollTo(0, 0);
    }, [location.pathname]);

    useEffect(() => {
        if (!menuOpen) return undefined;
        const onKey = (event) => {
            if (event.key === 'Escape') setMenuOpen(false);
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [menuOpen]);

    return h('div', { className: 'public-shell' },
        h('a', { href: '#public-main', className: 'skip-link' }, 'Skip to main content'),
        h('header', { className: 'public-header' },
            h('div', { className: 'public-header-inner' },
                h(Brand),
                h('button', {
                    type: 'button',
                    className: 'public-menu-toggle',
                    onClick: () => setMenuOpen((value) => !value),
                    'aria-label': menuOpen ? 'Close navigation menu' : 'Open navigation menu',
                    'aria-expanded': menuOpen,
                    'aria-controls': 'public-navigation'
                }, h(Icon, { name: menuOpen ? 'close' : 'menu', size: 22 })),
                h('nav', {
                    id: 'public-navigation',
                    className: 'public-nav' + (menuOpen ? ' is-open' : ''),
                    'aria-label': 'Main navigation'
                },
                    ...publicLinks.map(([to, label]) => h(NavLink, {
                        key: to,
                        to,
                        end: to === '/',
                        onClick: () => setMenuOpen(false),
                        className: ({ isActive }) => 'public-nav-link' + (isActive ? ' is-active' : '')
                    }, label)),
                    !loading && (user
                        ? h(Link, { to: user.role === 'admin' ? '/dashboard' : '/student/account', className: 'button button-primary' }, 'Open workspace')
                        : h(React.Fragment, null,
                            h(Link, { to: '/login', className: 'public-signin' }, 'Sign in'),
                            h(Link, { to: '/register', className: 'button button-primary' }, 'Student access request')
                        )
                    )
                )
            )
        ),
        h('main', { id: 'public-main', className: 'public-main', tabIndex: -1 },
            error && h(Problem, { message: error }),
            h(PageErrorBoundary, { key: location.pathname, fallbackTo: '/' }, h(Outlet))
        ),
        h('footer', { className: 'public-footer' },
            h('div', { className: 'public-footer-inner' },
                h('div', { className: 'footer-brand-block' },
                    h(Brand, { light: true }),
                    h('p', null, 'A clearer way to manage student records and verify identity.'),
                    h('span', { className: 'footer-prototype' }, 'Academic software prototype')
                ),
                h('div', { className: 'footer-column' },
                    h('h2', null, 'Explore'),
                    h(Link, { to: '/how-it-works' }, 'How it works'),
                    h(Link, { to: '/about' }, 'About StudentVerifi'),
                    h(Link, { to: '/faq' }, 'Frequently asked questions')
                ),
                h('div', { className: 'footer-column' },
                    h('h2', null, 'Support'),
                    h(Link, { to: '/privacy' }, 'Privacy and responsible use'),
                    h(Link, { to: '/contact' }, 'Contact and support'),
                    h(Link, { to: '/register' }, 'Request student access')
                )
            ),
            h('div', { className: 'public-footer-bottom' },
                h('span', null, '© ' + new Date().getFullYear() + ' StudentVerifi'),
                h('span', null, 'Use only with authorised institutional records.')
            )
        )
    );
}

function SidebarLink({ item, close }) {
    const [to, label, icon] = item;
    const location = useLocation();
    const detailActive = to === '/students' && /^\/students\/\d+$/.test(location.pathname);
    return h(NavLink, {
        to,
        end: true,
        onClick: close,
        className: ({ isActive }) => 'sidebar-link' + ((isActive || detailActive) ? ' is-active' : '')
    }, h(Icon, { name: icon, size: 18 }), h('span', null, label));
}

function DashboardShell() {
    const { user, error, logout, inform } = useAuth();
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [isMobile, setIsMobile] = useState(false);
    const sidebarRef = React.useRef(null);
    const toggleRef = React.useRef(null);
    const navigate = useNavigate();
    const location = useLocation();
    const groups = user?.role === 'admin' ? adminGroups : studentGroups;
    const title = routeTitles[location.pathname] ||
        (location.pathname.startsWith('/students/') ? 'Student record' : 'Workspace');

    useEffect(() => {
        setSidebarOpen(false);
        document.getElementById('workspace-main')?.focus();
        window.scrollTo(0, 0);
        document.title = 'StudentVerifi · ' + title;
    }, [location.pathname, title]);

    useEffect(() => {
        const media = window.matchMedia('(max-width: 960px)');
        const update = () => setIsMobile(media.matches);
        update();
        media.addEventListener('change', update);
        return () => media.removeEventListener('change', update);
    }, []);

    useEffect(() => {
        if (sidebarRef.current) {
            sidebarRef.current.inert = isMobile && !sidebarOpen;
        }
        if (sidebarOpen && isMobile) {
            sidebarRef.current?.querySelector('a[href]')?.focus();
        }
    }, [isMobile, sidebarOpen]);

    useEffect(() => {
        if (!sidebarOpen) return undefined;
        const onKey = (event) => {
            if (event.key === 'Escape') {
                setSidebarOpen(false);
                toggleRef.current?.focus();
                return;
            }
            if (event.key === 'Tab' && sidebarRef.current) {
                const controls = [...sidebarRef.current.querySelectorAll('a[href]')];
                if (!controls.length) return;
                if (event.shiftKey && document.activeElement === controls[0]) {
                    event.preventDefault();
                    controls[controls.length - 1].focus();
                } else if (!event.shiftKey && document.activeElement === controls[controls.length - 1]) {
                    event.preventDefault();
                    controls[0].focus();
                }
            }
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [sidebarOpen]);

    async function signOut() {
        try {
            await logout();
            navigate('/login', { replace: true });
            inform('You have signed out.');
        } catch (requestError) {
            inform(requestError.message, 'error');
        }
    }

    const closeSidebar = () => setSidebarOpen(false);
    const dismissSidebar = () => {
        setSidebarOpen(false);
        toggleRef.current?.focus();
    };

    return h('div', { className: 'workspace-shell' },
        h('a', { href: '#workspace-main', className: 'skip-link' }, 'Skip to main content'),
        sidebarOpen && h('button', {
            type: 'button',
            className: 'sidebar-backdrop',
            onClick: dismissSidebar,
            'aria-label': 'Close navigation'
        }),
        h('aside', {
            ref: sidebarRef,
            className: 'app-sidebar' + (sidebarOpen ? ' sidebar-open' : ''),
            id: 'workspace-sidebar',
            'aria-label': 'Workspace navigation',
            'aria-hidden': isMobile && !sidebarOpen
        },
            h('div', { className: 'sidebar-brand' },
                h(Brand, { light: true }),
                h('span', { className: 'sidebar-edition' }, 'IDENTITY MANAGEMENT')
            ),
            h('nav', { className: 'sidebar-navigation', 'aria-label': 'Workspace sections' },
                ...groups.map((group) => h('div', { className: 'sidebar-group', key: group.label },
                    h('p', { className: 'sidebar-group-label' }, group.label),
                    ...group.links.map((item) => h(SidebarLink, {
                        key: item[0],
                        item,
                        close: closeSidebar
                    }))
                ))
            ),
            h('div', { className: 'sidebar-bottom' },
                h('div', { className: 'sidebar-help' },
                    h('span', { className: 'sidebar-help-icon' }, h(Icon, { name: 'help', size: 18 })),
                    h('div', null,
                        h('strong', null, 'Need assistance?'),
                        h(Link, { to: '/contact', onClick: closeSidebar }, 'View support information')
                    )
                ),
                h(Link, { to: '/', className: 'sidebar-public-link', onClick: closeSidebar },
                    h(Icon, { name: 'home', size: 17 }), 'Public website'
                )
            )
        ),
        h('div', { className: 'workspace-main-column' },
            h('header', { className: 'workspace-topbar' },
                h('div', { className: 'topbar-leading' },
                    h('button', {
                        type: 'button',
                        ref: toggleRef,
                        className: 'sidebar-toggle',
                        onClick: () => setSidebarOpen((value) => !value),
                        'aria-label': sidebarOpen ? 'Close navigation menu' : 'Open navigation menu',
                        'aria-expanded': sidebarOpen,
                        'aria-controls': 'workspace-sidebar'
                    }, h(Icon, { name: sidebarOpen ? 'close' : 'menu', size: 21 })),
                    h('div', { className: 'topbar-page' },
                        h('span', { className: 'topbar-context' }, 'STUDENTVERIFI WORKSPACE'),
                        h('strong', null, title)
                    )
                ),
                h('div', { className: 'topbar-account' },
                    h('div', { className: 'account-avatar', 'aria-hidden': 'true' }, (user?.username || 'U').slice(0, 1).toUpperCase()),
                    h('div', { className: 'account-meta' },
                        h('strong', null, user?.username || 'Account'),
                        h('span', null, user?.role === 'admin' ? 'Administrator' : 'Student account')
                    ),
                    h(Button, { variant: 'ghost', className: 'topbar-signout', onClick: signOut },
                        h(Icon, { name: 'logout', size: 17 }), h('span', null, 'Sign out')
                    )
                )
            ),
            h('main', { id: 'workspace-main', className: 'workspace-content', tabIndex: -1 },
                error && h(Problem, { message: error }),
                h(PageErrorBoundary, { key: location.pathname, fallbackTo: user?.role === 'admin' ? '/dashboard' : '/student/account' }, h(Outlet))
            ),
            h('footer', { className: 'workspace-footer' },
                h('span', null, 'StudentVerifi · Academic prototype'),
                h('span', null, 'Use only with authorised student records and approved staff access.')
            )
        )
    );
}

export function AppShell() {
    const { user } = useAuth();
    return user ? h(DashboardShell) : h(PublicShell);
}

export function Protected({ role }) {
    const { user, loading, logout } = useAuth();
    const navigate = useNavigate();

    if (loading) return h(Spinner, { label: 'Checking your access…' });
    if (!user) {
        return h('div', { className: 'center-block access-message' },
            h('span', { className: 'access-icon' }, h(Icon, { name: 'shield', size: 28 })),
            h('h1', null, 'Sign in required'),
            h('p', null, 'Sign in with an authorised account to continue.'),
            h(Link, { to: '/login', className: 'button button-primary' }, 'Sign in')
        );
    }
    if (role && user.role !== role) {
        return h('div', { className: 'center-block access-message' },
            h('span', { className: 'access-icon' }, h(Icon, { name: 'shield', size: 28 })),
            h('h1', null, 'Use the correct account'),
            h('p', null, `This page requires a ${role} account. Sign out before switching accounts.`),
            h(Button, {
                onClick: async () => {
                    await logout();
                    navigate('/login', { replace: true });
                }
            }, 'Switch account')
        );
    }
    return h(Outlet);
}
