import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api, compactDate, fetchPrivateImage } from './api.js';
import {
    h,
    useAuth,
    Icon,
    Button,
    Panel,
    TitleBlock,
    Pill,
    Field,
    Problem,
    Empty,
    Spinner,
    ConfirmAction
} from './components.js';

const el = (tag, props, ...children) => h(tag, props, ...children);
const group = (...children) => h(React.Fragment, null, ...children);
const workspacePath = (role) => role === 'admin' ? '/dashboard' : role === 'verifier' ? '/verify' : '/student/account';

function useResource(path) {
    const [value, setValue] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [nonce, setNonce] = useState(0);

    useEffect(() => {
        const controller = new AbortController();
        setLoading(true);
        setError('');
        api(path, { signal: controller.signal })
            .then(setValue)
            .catch((requestError) => {
                if (requestError.name !== 'AbortError') setError(requestError.message);
            })
            .finally(() => {
                if (!controller.signal.aborted) setLoading(false);
            });
        return () => controller.abort();
    }, [path, nonce]);

    return { value, loading, error, reload: () => setNonce((current) => current + 1) };
}

function PrivatePhoto({
    src,
    alt,
    className = 'profile-image',
    placeholderClassName = 'profile-placeholder',
    fallbackText = '?'
}) {
    const [imageUrl, setImageUrl] = useState('');
    const [status, setStatus] = useState(src ? 'loading' : 'missing');
    const [retry, setRetry] = useState(0);

    useEffect(() => {
        const controller = new AbortController();
        let active = true;
        let objectUrl = '';

        setImageUrl('');
        if (!src) {
            setStatus('missing');
            return () => controller.abort();
        }

        setStatus('loading');
        fetchPrivateImage(src, { signal: controller.signal })
            .then((blob) => {
                if (!active) {
                    return;
                }
                objectUrl = URL.createObjectURL(blob);
                setImageUrl(objectUrl);
                setStatus('ready');
            })
            .catch((error) => {
                if (!active || error.name === 'AbortError') {
                    return;
                }
                console.warn('StudentVerifi private photo request failed.', {
                    status: Number.isInteger(error.status) ? error.status : 0
                });
                setStatus('error');
            });

        return () => {
            active = false;
            controller.abort();
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
            }
        };
    }, [src, retry]);

    if (status === 'ready' && imageUrl) {
        return el('img', {
            src: imageUrl,
            alt,
            className,
            onError: () => {
                URL.revokeObjectURL(imageUrl);
                setImageUrl('');
                setStatus('error');
            }
        });
    }

    const fallback = fallbackText || h(Icon, { name: 'user', size: 28 });
    if (status === 'error') {
        return el('div', { className: placeholderClassName },
            el('span', { 'aria-hidden': 'true' }, fallback),
            el('button', {
                type: 'button',
                className: 'photo-retry',
                onClick: () => setRetry((current) => current + 1),
                'aria-label': 'Retry loading profile photograph',
                title: 'Retry loading photograph'
            }, '↻')
        );
    }

    return el('div', {
        className: placeholderClassName + (status === 'loading' ? ' photo-loading' : ''),
        role: 'img',
        'aria-label': status === 'loading' ? `Loading ${alt.toLowerCase()}` : `${alt} not provided`
    }, fallback);
}

function getInput(setter, field) {
    return (event) => setter((current) => ({ ...current, [field]: event.target.value }));
}

function FormActions({ children }) {
    return el('div', { className: 'form-actions' }, children);
}

function DetailRow({ label, value }) {
    return group(el('dt', null, label), el('dd', null, value || '—'));
}

function InlineLink({ to, children }) {
    return h(Link, { to, className: 'text-link' }, children);
}

function SectionHeading({ eyebrow, title, description, centered = false }) {
    return el('div', { className: 'section-heading' + (centered ? ' is-centered' : '') },
        eyebrow && el('p', { className: 'eyebrow' }, eyebrow),
        el('h2', null, title),
        description && el('p', null, description)
    );
}

function Stat({ value, label, icon, tone = 'blue', note }) {
    return el('article', { className: 'stat-card stat-' + tone },
        el('div', { className: 'stat-card-top' },
            el('span', { className: 'stat-icon' }, h(Icon, { name: icon, size: 20 })),
            note && el('span', { className: 'stat-note' }, note)
        ),
        el('strong', { className: 'stat-value' }, value ?? '—'),
        el('span', { className: 'stat-label' }, label)
    );
}

export function Home() {
    const features = [
        ['verify', 'Confident identity checks', 'Scan a student QR credential or enter its code manually. The system checks the current record and returns a clear result.'],
        ['students', 'One organised student register', 'Search, review, update and import student records from a single protected workspace.'],
        ['mail', 'Self-service account claiming', 'Students verify the email already associated with their record, upload a profile photograph and activate their account automatically.'],
        ['history', 'Accountable activity', 'Verification outcomes and important administrative actions are recorded for later review.']
    ];
    const steps = [
        ['01', 'Register the student', 'An authorised administrator adds a student record or imports a validated register.'],
        ['02', 'Verify the registered email', 'The system sends a one-time code to the email address already associated with the student record.'],
        ['03', 'Complete the student profile', 'The student uploads a photograph and creates a password. Account activation and QR generation then happen automatically.'],
        ['04', 'Verify when needed', 'An authorised verifier scans the QR credential and independently checks the person’s identity.']
    ];

    return group(
        el('section', { className: 'hero' },
            el('div', { className: 'hero-copy' },
                el('p', { className: 'eyebrow eyebrow-light' }, 'STUDENT IDENTITY, MADE CLEARER'),
                el('h1', null, 'Student records and identity checks, brought together.'),
                el('p', { className: 'hero-subtitle' }, 'StudentVerifi gives authorised administrators and verifiers a clearer way to manage student records, issue QR credentials and confirm registration status.'),
                el('div', { className: 'hero-actions' },
                    h(Link, { to: '/login', className: 'button button-light' }, 'Sign in to workspace', h(Icon, { name: 'arrow', size: 17 })),
                    h(Link, { to: '/how-it-works', className: 'hero-secondary-link' }, 'Explore how it works')
                ),
                el('div', { className: 'hero-assurance' },
                    h(Icon, { name: 'shield', size: 17 }),
                    el('span', null, 'Role-based access · One-time student claims · Reviewable activity')
                )
            ),
            el('div', { className: 'hero-visual', 'aria-label': 'Illustration of a student verification result' },
                el('div', { className: 'hero-orbit hero-orbit-one' }),
                el('div', { className: 'hero-orbit hero-orbit-two' }),
                el('div', { className: 'verification-preview' },
                    el('div', { className: 'preview-topline' },
                        el('span', { className: 'preview-label' }, 'VERIFICATION RESULT'),
                        el('span', { className: 'preview-live' }, 'RECORD CHECK')
                    ),
                    el('div', { className: 'preview-profile' },
                        el('div', { className: 'preview-avatar' }, h(Icon, { name: 'user', size: 28 })),
                        el('div', null, el('strong', null, 'Student record'), el('span', null, 'Identity status review'))
                    ),
                    el('div', { className: 'preview-status' },
                        el('span', { className: 'preview-status-icon' }, h(Icon, { name: 'check', size: 18 })),
                        el('div', null, el('strong', null, 'Active record'), el('span', null, 'Current status confirmed'))
                    ),
                    el('div', { className: 'preview-lines' }, el('span'), el('span'), el('span')),
                    el('div', { className: 'preview-footer' }, h(Icon, { name: 'shield', size: 15 }), 'Verify the person independently')
                ),
                el('div', { className: 'hero-floating-note' }, h(Icon, { name: 'history', size: 17 }), 'Traceable verification activity')
            )
        ),
        el('section', { className: 'public-section feature-section' },
            h(SectionHeading, {
                eyebrow: 'A CONNECTED WORKFLOW',
                title: 'The essential tools in one place',
                description: 'Purpose-built features support the everyday work of student record management and identity verification.'
            }),
            el('div', { className: 'feature-grid' },
                ...features.map(([icon, title, text], index) => el('article', { className: 'feature-card', key: title },
                    el('span', { className: 'feature-icon' }, h(Icon, { name: icon, size: 22 })),
                    el('span', { className: 'feature-index' }, '0' + (index + 1)),
                    el('h3', null, title),
                    el('p', null, text)
                ))
            )
        ),
        el('section', { className: 'public-section workflow-section' },
            h(SectionHeading, {
                eyebrow: 'HOW THE PROCESS WORKS',
                title: 'A clear path from record to verification',
                description: 'Each stage has a defined purpose, helping administrators keep access controlled and verifiers make informed decisions.'
            }),
            el('div', { className: 'workflow-grid' },
                ...steps.map(([number, title, text]) => el('article', { className: 'workflow-step', key: number },
                    el('span', { className: 'workflow-number' }, number),
                    el('h3', null, title),
                    el('p', null, text)
                ))
            )
        ),
        el('section', { className: 'public-section trust-section' },
            el('div', { className: 'trust-copy' },
                el('p', { className: 'eyebrow' }, 'RESPONSIBLE VERIFICATION'),
                el('h2', null, 'A QR code is a starting point, not proof of identity.'),
                el('p', null, 'A successful scan confirms that a credential matches a current student record. It does not prove who is holding the phone or printed code. Verifiers should compare the result with approved identification or another reliable identity source.'),
                h(Link, { to: '/privacy', className: 'text-link' }, 'Read about responsible use', h(Icon, { name: 'arrow', size: 16 }))
            ),
            el('div', { className: 'trust-points' },
                ...[
                    ['shield', 'Access controls', 'Administrator and student functions are separated by account role.'],
                    ['mail', 'Verified account claims', 'Email verification and mandatory profile completion protect student account activation.'],
                    ['audit', 'Activity records', 'Important verification and administrative actions can be reviewed.']
                ].map(([icon, title, text]) => el('div', { className: 'trust-point', key: title },
                    el('span', { className: 'trust-point-icon' }, h(Icon, { name: icon, size: 20 })),
                    el('div', null, el('strong', null, title), el('p', null, text))
                ))
            )
        ),
        el('section', { className: 'public-callout' },
            el('div', null,
                el('p', { className: 'eyebrow eyebrow-light' }, 'STUDENTVERIFI'),
                el('h2', null, 'Ready to access your workspace?'),
                el('p', null, 'Administrators and authorised verifiers can sign in. Students can claim an existing record using its registered email address.')
            ),
            h(Link, { to: '/login', className: 'button button-light' }, 'Go to sign in', h(Icon, { name: 'arrow', size: 17 }))
        ),
        el('p', { className: 'prototype-disclaimer' }, 'StudentVerifi is an academic software prototype. Use with genuine institutional records only after obtaining the appropriate authorisation and establishing suitable data-protection procedures.')
    );
}

const infoContent = {
    '/how-it-works': {
        eyebrow: 'THE PROCESS',
        title: 'How StudentVerifi works',
        intro: 'StudentVerifi connects the student register, account access and QR-assisted identity checks in a controlled workflow.',
        sections: [
            ['students', '1. Maintain the student register', 'An administrator creates individual records or imports a validated CSV file from an authorised institutional source.'],
            ['mail', '2. Verify the registered email', 'The student enters the matriculation number and email already stored on the record. A one-time code is sent to that address.'],
            ['camera', '3. Complete the profile', 'The student uploads a profile photograph and creates a password. The account activates automatically after successful verification.'],
            ['verify', '4. Scan or open the QR credential', 'An authorised verifier can scan from the workspace. A visitor outside the institution can use an ordinary phone camera to open a limited public verification result.'],
            ['history', '5. Review the outcome', 'The system reports the current record status and records verification activity for authorised review.']
        ],
        notice: 'A valid QR credential confirms a matching record. It does not establish that the person presenting it is the student. Always perform an independent identity check.'
    },
    '/about': {
        eyebrow: 'ABOUT THE PLATFORM',
        title: 'A practical approach to student identity management',
        intro: 'StudentVerifi is a university-oriented academic prototype designed to make student record management and QR-assisted verification easier to organise.',
        sections: [
            ['book', 'Why it exists', 'Student identity checks can involve searching records, interpreting physical identification and recording outcomes. StudentVerifi brings the register and verification workflow into one web application.'],
            ['users', 'Who uses it', 'Administrators manage records and verifier access. Lecturers and authorised staff use separate verifier accounts. Students claim existing records and access their digital student card. External visitors can open limited QR verification results without an account.'],
            ['shield', 'How access is controlled', 'The application separates administrator, verifier and student permissions. Public QR checks disclose only limited identity information. Students verify the email already stored on their record before activating an account.'],
            ['check', 'What it is not', 'StudentVerifi is not an official university identity authority by itself. Its reliability depends on authorised source records and appropriate institutional procedures.']
        ],
        notice: 'The prototype should be formally reviewed and authorised by the institution before it is used to make official student identity or eligibility decisions.'
    },
    '/privacy': {
        eyebrow: 'PRIVACY AND RESPONSIBLE USE',
        title: 'Protecting student information',
        intro: 'StudentVerifi handles identity-related information. Its use must be governed by institutional authorisation, appropriate access controls and clear data-handling procedures.',
        sections: [
            ['lock', 'Limit access', 'Only authorised administrators and verifiers should use functions that expose student records. Students should only access their own account information.'],
            ['user', 'Use accurate source records', 'Student information should come from an approved institutional source. Incorrect or outdated records can produce misleading verification results.'],
            ['shield', 'Protect credentials', 'Passwords, email verification codes and QR credentials should not be shared publicly. Administrators should rotate credentials if they are compromised.'],
            ['camera', 'Profile photographs', 'Student photographs are stored in private file storage and are served through application routes. New account claims require a photograph before QR credentials are issued.'],
            ['globe', 'Public QR checks', 'A public QR check shows only the student name, masked matriculation number, institution, profile photograph and credential status. It does not expose email, telephone number, address or full academic record.'],
            ['history', 'Retain activity responsibly', 'The institution should define retention periods, access rights and procedures for handling correction or deletion requests.'],
            ['file', 'Institutional responsibility', 'Before genuine student data is loaded, the institution should approve the purpose of processing, provide an appropriate privacy notice and establish backups and retention procedures.']
        ],
        notice: 'This page describes responsible-use principles for the prototype. It is not a substitute for an institution-approved privacy notice or legal assessment.'
    },
    '/contact': {
        eyebrow: 'SUPPORT',
        title: 'Contact and support',
        intro: 'For account access, student record corrections or verification concerns, contact the administrator responsible for your StudentVerifi installation.',
        sections: [
            ['user', 'Student account access', 'Ask the administrator to confirm that your record and email address are correct. Then use the account-claim page to receive a one-time code at the email address on file.'],
            ['book', 'Student record correction', 'If your name, matriculation number, faculty, department or level is incorrect, ask an authorised administrator to check the source register.'],
            ['verify', 'QR and camera support', 'Allow camera access in your browser, select the rear camera where available and use manual entry if scanning is unavailable.'],
            ['shield', 'Security concerns', 'Report a lost QR credential, suspected account access or incorrect verification outcome promptly. Never include a password or email verification code in a support message.']
        ],
        notice: 'No public support email or telephone number has been configured in this prototype. Use the institution’s approved support channel.'
    }
};

const faqItems = [
    ['Can any student create an account?', 'No. The student must already have a record in the register and access the email address stored on that record. After verifying the one-time code, uploading a photograph and creating a password, the account is activated automatically.'],
    ['What if my email address is missing or incorrect?', 'Contact the administrator responsible for StudentVerifi and ask them to add or correct the email address on your existing student record.'],
    ['Why can I not receive an account-claim code?', 'The matriculation number and email must match one unclaimed active student record. The email must be unique to that record. Contact the administrator if your email is missing, incorrect or shared with another student record.'],
    ['What if I already have an account?', 'Use the sign-in page with your matriculation number or account username and password. If you cannot access the account, contact the administrator.'],
    ['Why does my QR code not verify?', 'The student record may be inactive, the credential may have been rotated, or the code may not match a current record. Ask an authorised administrator to review it.'],
    ['Does scanning a valid QR code prove the holder is the student?', 'No. A QR scan checks the credential against the student register. The verifier must independently compare the person with approved identification or another reliable identity source.'],
    ['Can someone outside the institution verify a student?', 'Yes. The person can scan the student QR code with an ordinary smartphone camera. The link opens a limited public result showing the student name, masked matriculation number, institution, photograph and credential status. No account is required.'],
    ['Does a lecturer need administrator access to verify students?', 'No. An administrator can invite the lecturer as a verifier. A verifier can scan QR credentials and review their own verification activity but cannot manage student records or administrator settings.'],
    ['Can I use StudentVerifi on a phone?', 'Yes. The interface adapts to mobile screens. QR scanning requires a supported browser, camera permission and a secure HTTPS connection.']
];

export function InfoPage({ page }) {
    if (page === '/faq') {
        return group(
            el('section', { className: 'info-hero' },
                el('p', { className: 'eyebrow' }, 'HELP CENTRE'),
                el('h1', null, 'Frequently asked questions'),
                el('p', { className: 'lead' }, 'Answers to common questions about student access, QR credentials and identity verification.')
            ),
            el('section', { className: 'faq-list', 'aria-label': 'Frequently asked questions' },
                ...faqItems.map(([question, answer], index) => el('details', { className: 'faq-item', key: question },
                    el('summary', null,
                        el('span', { className: 'faq-number' }, String(index + 1).padStart(2, '0')),
                        el('span', null, question),
                        h(Icon, { name: 'plus', size: 18 })
                    ),
                    el('p', null, answer)
                ))
            ),
            el('aside', { className: 'info-notice', role: 'note' },
                h(Icon, { name: 'shield', size: 20 }),
                el('p', null, 'For a question about a specific student record or account, contact the administrator for your installation. Do not share passwords or email verification codes.')
            )
        );
    }

    const data = infoContent[page] || infoContent['/about'];
    return group(
        el('section', { className: 'info-hero' },
            el('p', { className: 'eyebrow' }, data.eyebrow),
            el('h1', null, data.title),
            el('p', { className: 'lead' }, data.intro)
        ),
        el('section', { className: 'info-grid' },
            ...data.sections.map(([icon, title, text]) => el('article', { className: 'info-card', key: title },
                el('span', { className: 'info-card-icon' }, h(Icon, { name: icon, size: 21 })),
                el('h2', null, title),
                el('p', null, text)
            ))
        ),
        el('aside', { className: 'info-notice', role: 'note' },
            h(Icon, { name: 'shield', size: 20 }),
            el('p', null, data.notice)
        ),
        el('div', { className: 'info-bottom-actions' },
            h(Link, { to: '/login', className: 'button button-primary' }, 'Sign in to StudentVerifi'),
            h(Link, { to: '/contact', className: 'text-link' }, 'Contact and support', h(Icon, { name: 'arrow', size: 16 }))
        )
    );
}

export function Login() {
    const { user, login, logout, inform } = useAuth();
    const navigate = useNavigate();
    const [form, setForm] = useState({ username: '', password: '' });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    async function submit(event) {
        event.preventDefault();
        setError('');
        setBusy(true);
        try {
            const result = await login(form.username, form.password);
            inform('Signed in successfully.');
            navigate(workspacePath(result.role), { replace: true });
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    return el('div', { className: 'auth-layout' },
        el('section', { className: 'auth-intro' },
            el('p', { className: 'eyebrow' }, 'YOUR SECURE WORKSPACE'),
            el('h1', null, 'Welcome back to StudentVerifi.'),
            el('p', { className: 'lead' }, 'Sign in to continue to student records, authorised verification tools or your student card.'),
            el('div', { className: 'auth-benefits' },
                ...[
                    ['shield', 'Protected access', 'Administrator, verifier and student accounts have separate permissions.'],
                    ['history', 'Clear activity records', 'Verification outcomes and administrative actions are recorded.'],
                    ['verify', 'Mobile-ready verification', 'Authorised verifiers can scan QR credentials from a supported phone browser.']
                ].map(([icon, title, text]) => el('div', { className: 'auth-benefit', key: title },
                    h(Icon, { name: icon, size: 19 }),
                    el('div', null, el('strong', null, title), el('span', null, text))
                ))
            )
        ),
        h(Panel, { className: 'auth-panel' },
            user
                ? el('div', { className: 'form-stack' },
                    el('span', { className: 'auth-panel-icon' }, h(Icon, { name: 'user', size: 23 })),
                    el('h2', null, 'You are already signed in'),
                    el('p', null, 'Signed in as ' + (user.display_name || user.username) + '.'),
                    h(Link, {
                        to: workspacePath(user.role),
                        className: 'button button-primary button-full'
                    }, 'Continue to workspace'),
                    h(Button, {
                        variant: 'outline',
                        onClick: async () => {
                            await logout();
                            inform('You can now sign in with another account.');
                        }
                    }, 'Switch account')
                )
                : el('form', { onSubmit: submit, className: 'form-stack' },
                    el('div', { className: 'auth-panel-heading' },
                        el('p', { className: 'eyebrow' }, 'ACCOUNT ACCESS'),
                        el('h2', null, 'Sign in'),
                        el('p', null, 'Administrators use their username, verifiers use their invited email address, and students use their matriculation number.')
                    ),
                    h(Problem, { message: error }),
                    h(Field, {
                        label: 'Username, email or matriculation number',
                        name: 'username',
                        autoComplete: 'username',
                        value: form.username,
                        onChange: getInput(setForm, 'username'),
                        required: true
                    }),
                    h(Field, {
                        label: 'Password',
                        name: 'password',
                        type: 'password',
                        autoComplete: 'current-password',
                        value: form.password,
                        onChange: getInput(setForm, 'password'),
                        required: true
                    }),
                    h(Button, { type: 'submit', busy, className: 'button-full' }, 'Sign in securely'),
                    el('p', { className: 'form-note' }, 'Student without an account? ', h(InlineLink, { to: '/register' }, 'Claim your student account'))
                )
        )
    );
}

export function Register() {
    const { setUser, inform } = useAuth();
    const navigate = useNavigate();
    const [step, setStep] = useState(1);
    const [form, setForm] = useState({ matric_no: '', email: '', otp: '', password: '', confirm: '' });
    const [photo, setPhoto] = useState(null);
    const [preview, setPreview] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');

    useEffect(() => {
        if (!photo) {
            setPreview('');
            return undefined;
        }
        const url = URL.createObjectURL(photo);
        setPreview(url);
        return () => URL.revokeObjectURL(url);
    }, [photo]);

    async function startClaim(event) {
        event.preventDefault();
        setError('');
        setNotice('');
        setBusy(true);
        try {
            const result = await api('/claim/start', {
                method: 'POST',
                body: { matric_no: form.matric_no, email: form.email }
            });
            setForm(previous => ({ ...previous, otp: '' }));
            setNotice(result.message);
            setStep(2);
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    async function verifyCode(event) {
        event.preventDefault();
        setError('');
        setBusy(true);
        try {
            const result = await api('/claim/verify', {
                method: 'POST',
                body: { matric_no: form.matric_no, otp: form.otp }
            });
            setNotice('');
            setStep(3);
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    async function completeClaim(event) {
        event.preventDefault();
        setError('');
        if (!photo) {
            setError('Upload a clear profile photograph before continuing.');
            return;
        }
        if (form.password !== form.confirm) {
            setError('The passwords do not match.');
            return;
        }
        const payload = new FormData();
        payload.append('photo', photo);
        payload.append('password', form.password);
        payload.append('confirm', form.confirm);
        setBusy(true);
        try {
            const result = await api('/claim/complete', { method: 'POST', body: payload });
            setUser(result.user);
            inform(result.message);
            navigate('/student/account', { replace: true });
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    return el('div', { className: 'registration-layout claim-focused' },
        h(Panel, { className: 'registration-panel claim-focused-panel' },
            el('div', { className: 'claim-brand' },
                el('img', { src: '/logo.svg', alt: 'StudentVerifi', width: 210, height: 49 })
            ),
            h(Problem, { message: error }),
            notice && el('p', { className: 'alert alert-info', role: 'status' }, notice),
            step === 1 && el('form', { key: 1, onSubmit: startClaim, className: 'form-stack claim-stage' },
                el('div', { className: 'auth-panel-heading' },
                    el('h1', null, 'Claim your student account'),
                    el('p', null, 'The email address must match the one already associated with your student record.')
                ),
                h(Field, {
                    label: 'Matriculation number', name: 'matric_no', required: true,
                    value: form.matric_no, onChange: getInput(setForm, 'matric_no'),
                    autoComplete: 'off', maxLength: 50, placeholder: 'Enter your matriculation number'
                }),
                h(Field, {
                    label: 'Registered email address', name: 'email', type: 'email', required: true,
                    value: form.email, onChange: getInput(setForm, 'email'),
                    autoComplete: 'email', maxLength: 254, placeholder: 'Enter the email on your student record'
                }),
                h(Button, { type: 'submit', busy, className: 'button-full' }, 'Send verification code')
            ),
            step === 2 && el('form', { key: 2, onSubmit: verifyCode, className: 'form-stack claim-stage' },
                el('div', { className: 'auth-panel-heading' },
                    el('h1', null, 'Verify your email'),
                    el('p', null, 'Enter the six-digit code sent to the email address associated with your student record. The code expires after 10 minutes.')
                ),
                h(Field, {
                    label: 'Six-digit verification code', name: 'otp', required: true,
                    value: form.otp, onChange: getInput(setForm, 'otp'),
                    inputMode: 'numeric', autoComplete: 'one-time-code', maxLength: 6,
                    placeholder: '000000'
                }),
                h(Button, { type: 'submit', busy, className: 'button-full' }, 'Verify email'),
                h(Button, { variant: 'outline', disabled: busy, onClick: () => { setNotice(''); setError(''); setStep(1); } }, 'Change email or matriculation number'),
                h(Button, { variant: 'ghost', disabled: busy, onClick: startClaim }, 'Resend verification code')
            ),
            step === 3 && el('form', { key: 3, onSubmit: completeClaim, className: 'form-stack claim-stage' },
                el('div', { className: 'auth-panel-heading' },
                    el('h1', null, 'Complete your profile'),
                    el('p', null, 'A profile photograph is required before your account and QR credential can be activated.')
                ),
                el('label', { className: 'photo-upload-field' },
                    el('span', { className: 'photo-upload-preview' },
                        preview
                            ? el('img', { src: preview, alt: 'Selected profile photograph preview' })
                            : h(Icon, { name: 'camera', size: 30 })
                    ),
                    el('strong', null, photo ? photo.name : 'Choose your profile photograph'),
                    el('small', null, 'JPEG, PNG or WebP · Maximum 2 MB · Clear face photograph'),
                    el('input', {
                        type: 'file',
                        accept: 'image/jpeg,image/png,image/webp',
                        required: true,
                        onChange: (event) => setPhoto(event.target.files?.[0] || null)
                    })
                ),
                h(Field, {
                    label: 'Create a password', name: 'password', type: 'password',
                    minLength: 12, maxLength: 128, required: true, autoComplete: 'new-password',
                    value: form.password, onChange: getInput(setForm, 'password'),
                    hint: 'Use at least 12 characters.'
                }),
                h(Field, {
                    label: 'Confirm password', name: 'confirm', type: 'password',
                    required: true, autoComplete: 'new-password',
                    value: form.confirm, onChange: getInput(setForm, 'confirm')
                }),
                h(Button, { type: 'submit', busy, className: 'button-full' }, 'Activate my account')
            ),
            el('p', { className: 'form-note' }, 'Already have an account? ', h(InlineLink, { to: '/login' }, 'Sign in instead'))
        )
    );
}

export function Dashboard() {
    const { value, loading, error } = useResource('/dashboard');
    const total = Number(value?.students || 0);
    const active = Number(value?.active || 0);
    const activeRate = total ? Math.round((active / total) * 100) : 0;
    const recent = value?.recent || [];
    const weekly = value?.weekly_verifications || [];
    const faculty = value?.faculty_summary || [];
    const weeklyMax = Math.max(1, ...weekly.map((item) => Number(item.total || 0)));
    const facultyMax = Math.max(1, ...faculty.map((item) => Number(item.total || 0)));

    return group(
        h(TitleBlock, {
            eyebrow: 'ADMINISTRATOR OVERVIEW',
            title: 'Good to see you.',
            description: 'A live overview of student records, account claims, verifier access and verification activity.',
            actions: h(Link, { className: 'button button-primary', to: '/verify' }, h(Icon, { name: 'verify', size: 17 }), 'Verify a student')
        }),
        h(Problem, { message: error }),
        loading
            ? h(Spinner, { label: 'Loading your workspace overview…' })
            : value && group(
                el('section', { className: 'stats-grid', 'aria-label': 'StudentVerifi statistics' },
                    h(Stat, { value: total.toLocaleString(), label: 'Students in register', icon: 'students', tone: 'blue', note: 'Total records' }),
                    h(Stat, { value: active.toLocaleString(), label: 'Active students', icon: 'check', tone: 'green', note: activeRate + '% active' }),
                    h(Stat, { value: Number(value.unclaimed || 0).toLocaleString(), label: 'Unclaimed student records', icon: 'user', tone: 'amber', note: 'Awaiting student claim' }),
                    h(Stat, { value: Number(value.claimed || 0).toLocaleString(), label: 'Claimed accounts', icon: 'check', tone: 'green', note: 'Student accounts' }),
                    h(Stat, { value: Number(value.verifiers || 0).toLocaleString(), label: 'Active verifiers', icon: 'verifier', tone: 'blue', note: 'Authorised staff' }),
                    h(Stat, { value: Number(value.verifications || 0).toLocaleString(), label: 'Verification events', icon: 'history', tone: 'violet', note: 'Recorded checks' })
                ),
                el('section', { className: 'dashboard-main-grid' },
                    h(Panel, { className: 'dashboard-panel activity-panel' },
                        el('div', { className: 'panel-heading-row' },
                            el('div', null, el('p', { className: 'eyebrow' }, 'LATEST ACTIVITY'), el('h2', null, 'Recent verification checks'), el('p', { className: 'muted' }, 'The latest recorded verification outcomes.')),
                            h(Link, { to: '/verify', className: 'text-link' }, 'Open verification centre', h(Icon, { name: 'arrow', size: 15 }))
                        ),
                        recent.length
                            ? el('div', { className: 'activity-table-wrap' },
                                el('table', { className: 'activity-table' },
                                    el('thead', null, el('tr', null,
                                        el('th', { scope: 'col' }, 'Result'),
                                        el('th', { scope: 'col' }, 'Student / record'),
                                        el('th', { scope: 'col' }, 'Verified by'),
                                        el('th', { scope: 'col' }, 'Date and time')
                                    )),
                                    el('tbody', null, ...recent.map((item) => el('tr', { key: item.id },
                                        el('td', null, h(Pill, { status: item.result })),
                                        el('td', null, el('strong', null, item.full_name || item.matric_no || 'Unmatched code'), el('span', { className: 'table-secondary' }, item.matric_no || 'No student record')),
                                        el('td', null, item.verifier_name || (item.channel === 'public' ? 'Public visitor' : 'Former account')),
                                        el('td', null, compactDate(item.verified_at))
                                    )))
                                )
                            )
                            : h(Empty, { title: 'No verification activity yet', text: 'New verification checks will appear here after an authorised verifier scans a credential.' })
                    ),
                    el('div', { className: 'dashboard-side-stack' },
                        h(Panel, { className: 'dashboard-panel register-health' },
                            el('div', { className: 'panel-heading-row' }, el('div', null, el('p', { className: 'eyebrow' }, 'REGISTER HEALTH'), el('h2', null, 'Active student records')), h(Icon, { name: 'shield', size: 21 })),
                            el('div', { className: 'health-number' }, el('strong', null, activeRate + '%'), el('span', null, 'of student records are active')),
                            el('div', { className: 'health-track', role: 'progressbar', 'aria-label': 'Percentage of active student records', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': activeRate }, el('span', { style: { width: activeRate + '%' } })),
                            el('div', { className: 'health-legend' },
                                el('span', null, el('i', { className: 'legend-dot legend-active' }), active.toLocaleString() + ' active'),
                                el('span', null, el('i', { className: 'legend-dot legend-inactive' }), Number(value.inactive || 0).toLocaleString() + ' inactive')
                            ),
                            h(Link, { to: '/students', className: 'button button-outline button-full' }, 'Review student register')
                        ),
                        h(Panel, { className: 'dashboard-panel request-summary' },
                            el('div', { className: 'request-summary-icon' }, h(Icon, { name: 'requests', size: 22 })),
                            el('p', { className: 'eyebrow' }, 'ACCOUNT ACCESS'),
                            el('h2', null, Number(value.pending || 0).toLocaleString(), ' legacy requests'),
                            el('p', null, 'Review historical claim-code requests created before automated email-based account claiming. New claims activate automatically after email and profile verification.'),
                            h(Link, { to: '/registration-requests', className: 'button button-primary button-full' }, 'Open request history')
                        )
                    )
                ),
                el('section', { className: 'dashboard-insights-grid' },
                    h(Panel, { className: 'dashboard-panel insight-panel' },
                        el('div', { className: 'panel-heading-row' }, el('div', null, el('p', { className: 'eyebrow' }, 'SEVEN-DAY VIEW'), el('h2', null, 'Verification activity'), el('p', { className: 'muted' }, 'Recorded checks for the last seven days.')), h(Icon, { name: 'history', size: 21 })),
                        weekly.length
                            ? el('div', { className: 'trend-chart', role: 'img', 'aria-label': weekly.map((item) => item.label + ': ' + item.total + ' verifications').join('; ') },
                                ...weekly.map((item) => {
                                    const count = Number(item.total || 0);
                                    const height = count ? Math.max(7, Math.round((count / weeklyMax) * 100)) : 3;
                                    return el('div', { className: 'trend-column', key: item.date },
                                        el('span', { className: 'trend-count' }, count),
                                        el('div', { className: 'trend-bar-track' }, el('span', { className: 'trend-bar', style: { height: height + '%' } })),
                                        el('span', { className: 'trend-label' }, item.label)
                                    );
                                })
                            )
                            : h(Empty, { title: 'No activity data', text: 'Verification activity will appear here.' })
                    ),
                    h(Panel, { className: 'dashboard-panel insight-panel' },
                        el('div', { className: 'panel-heading-row' }, el('div', null, el('p', { className: 'eyebrow' }, 'RECORD DISTRIBUTION'), el('h2', null, 'Students by faculty'), el('p', { className: 'muted' }, 'The largest faculty groups in the register.')), h(Icon, { name: 'book', size: 21 })),
                        faculty.length
                            ? el('div', { className: 'faculty-bars' },
                                ...faculty.map((item) => {
                                    const count = Number(item.total || 0);
                                    const width = Math.round((count / facultyMax) * 100);
                                    return el('div', { className: 'faculty-bar-row', key: item.faculty },
                                        el('div', { className: 'faculty-bar-label' }, el('span', null, item.faculty), el('strong', null, count.toLocaleString())),
                                        el('div', { className: 'faculty-bar-track', role: 'progressbar', 'aria-label': item.faculty, 'aria-valuemin': 0, 'aria-valuemax': facultyMax, 'aria-valuenow': count }, el('span', { style: { width: width + '%' } }))
                                    );
                                })
                            )
                            : h(Empty, { title: 'No faculty records', text: 'Faculty distribution will appear when student records are available.' })
                    )
                ),
                el('section', { className: 'quick-actions-section' },
                    h(SectionHeading, { eyebrow: 'WORKSPACE SHORTCUTS', title: 'What would you like to do?', description: 'Jump directly to a common administrative task.' }),
                    el('div', { className: 'quick-actions-grid' },
                        ...[
                            ['/students', 'Student directory', 'Find a student and manage their record.', 'students'],
                            ['/students/new', 'Add a student', 'Create an individual student record.', 'plus'],
                            ['/students/import', 'Import records', 'Upload and validate a CSV register.', 'file'],
                            ['/verify', 'Verify identity', 'Scan a QR credential or enter a code.', 'verify']
                        ].map(([to, title, text, icon]) => h(Link, { to, className: 'quick-action-card', key: to },
                            el('span', { className: 'quick-action-icon' }, h(Icon, { name: icon, size: 20 })),
                            el('span', { className: 'quick-action-copy' }, el('strong', null, title), el('span', null, text)),
                            h(Icon, { name: 'arrow', size: 17 })
                        ))
                    )
                )
            )
    );
}

export function Students() {
    const [draft, setDraft] = useState('');
    const [query, setQuery] = useState('');
    const [page, setPage] = useState(1);
    const [status, setStatus] = useState('');
    const suffix = `/students?page=${page}&limit=20&q=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`;
    const { value, loading, error } = useResource(suffix);

    return group(
        h(TitleBlock, {
            eyebrow: 'STUDENT RECORDS',
            title: 'Student directory',
            description: 'Search student records, monitor account-claim status and manage each record.',
            actions: group(
                h(Link, { to: '/students/demo-cleanup', className: 'button button-outline' }, 'Test data'),
                h(Link, { to: '/students/import', className: 'button button-outline' }, 'Import CSV'),
                h(Link, { to: '/students/new', className: 'button button-primary' }, h(Icon, { name: 'plus', size: 17 }), 'Add student')
            )
        }),
        h(Panel, null,
            el('form', {
                className: 'search-bar',
                onSubmit: (event) => {
                    event.preventDefault();
                    setPage(1);
                    setQuery(draft);
                },
                role: 'search'
            },
                h(Field, {
                    label: 'Find a student',
                    name: 'student-search',
                    value: draft,
                    onChange: getInput(setDraft, 'value'),
                    placeholder: 'Name, matriculation number or department'
                }),
                h(Field, {
                    label: 'Record status',
                    name: 'status-filter',
                    select: true,
                    value: status,
                    onChange: (event) => {
                        setStatus(event.target.value);
                        setPage(1);
                    },
                    choices: ['Active', 'Inactive']
                }),
                h(Button, { type: 'submit' }, h(Icon, { name: 'search', size: 17 }), 'Search')
            ),
            h(Problem, { message: error }),
            loading
                ? h(Spinner)
                : value && group(
                    el('p', { className: 'results-count', role: 'status' },
                        `${value.total} student${value.total === 1 ? '' : 's'} found`
                    ),
                    value.items.length
                        ? el('div', { className: 'table-scroll' },
                            el('table', null,
                                el('thead', null,
                                    el('tr', null,
                                        ...['Student', 'Matriculation number', 'Faculty / department', 'Level', 'Record status', 'Account', 'Action'].map((label) =>
                                            el('th', { key: label, scope: 'col' }, label)
                                        )
                                    )
                                ),
                                el('tbody', null,
                                    ...value.items.map((student) => el('tr', { key: student.id },
                                        el('td', null, el('strong', null, student.name)),
                                        el('td', null, student.matric_no),
                                        el('td', null, student.faculty + ' · ' + student.department),
                                        el('td', null, student.level),
                                        el('td', null, h(Pill, { status: student.status })),
                                        el('td', null, h(Pill, { status: student.account_claimed ? 'Claimed' : student.email ? 'Unclaimed' : 'Email required' })),
                                        el('td', null, h(Link, {
                                            className: 'text-link',
                                            to: '/students/' + student.id
                                        }, 'View record'))
                                    ))
                                )
                            )
                        )
                        : h(Empty, {
                            title: 'No matching students',
                            text: 'Try another search or add a student record.'
                        }),
                    el('nav', { className: 'pagination', 'aria-label': 'Student pages' },
                        h(Button, {
                            variant: 'outline',
                            disabled: page === 1,
                            onClick: () => setPage((current) => Math.max(1, current - 1))
                        }, 'Previous'),
                        el('span', null, `Page ${page} of ${Math.max(1, Math.ceil(value.total / 20))}`),
                        h(Button, {
                            variant: 'outline',
                            disabled: page * 20 >= value.total,
                            onClick: () => setPage((current) => current + 1)
                        }, 'Next')
                    )
                )
        )
    );
}

export function StudentForm() {
    const { inform } = useAuth();
    const navigate = useNavigate();
    const [form, setForm] = useState({
        matric_no: '',
        first_name: '',
        middle_name: '',
        last_name: '',
        faculty: '',
        department: '',
        level: '',
        email: '',
        status: 'Active'
    });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const catalogue = useResource('/catalogue');
    const departmentChoices = catalogue.value?.faculty_departments?.[form.faculty] || [];

    async function submit(event) {
        event.preventDefault();
        setError('');
        setBusy(true);
        try {
            const result = await api('/students', { method: 'POST', body: form });
            inform('Student record created.');
            navigate('/students/' + result.id);
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    return group(
        h(TitleBlock, {
            eyebrow: 'STUDENT RECORDS',
            title: 'Add student',
            description: 'Create a student record using information from an authorised institutional register.'
        }),
        h(Panel, { className: 'form-panel' },
            el('form', { className: 'form-stack', onSubmit: submit },
                h(Problem, { message: error || catalogue.error }),
                el('div', { className: 'form-grid' },
                    h(Field, {
                        label: 'Matriculation number',
                        name: 'matric_no',
                        required: true,
                        value: form.matric_no,
                        onChange: getInput(setForm, 'matric_no')
                    }),
                    h(Field, {
                        label: 'First name',
                        name: 'first_name',
                        required: true,
                        value: form.first_name,
                        onChange: getInput(setForm, 'first_name')
                    }),
                    h(Field, {
                        label: 'Middle name (optional)',
                        name: 'middle_name',
                        value: form.middle_name,
                        onChange: getInput(setForm, 'middle_name')
                    }),
                    h(Field, {
                        label: 'Surname',
                        name: 'last_name',
                        required: true,
                        value: form.last_name,
                        onChange: getInput(setForm, 'last_name')
                    }),
                    h(Field, {
                        label: 'Faculty',
                        name: 'faculty',
                        required: true,
                        select: true,
                        choices: catalogue.value?.faculties || [],
                        value: form.faculty,
                        onChange: (event) => setForm((current) => ({
                            ...current,
                            faculty: event.target.value,
                            department: ''
                        }))
                    }),
                    h(Field, {
                        label: 'Department',
                        name: 'department',
                        required: true,
                        select: true,
                        choices: departmentChoices,
                        value: form.department,
                        onChange: getInput(setForm, 'department'),
                        disabled: !form.faculty || catalogue.loading
                    }),
                    h(Field, {
                        label: 'Level',
                        name: 'level',
                        select: true,
                        choices: ['100', '200', '300', '400', '500', '600'],
                        required: true,
                        value: form.level,
                        onChange: getInput(setForm, 'level')
                    }),
                    h(Field, {
                        label: 'Student email address',
                        name: 'email',
                        type: 'email',
                        value: form.email,
                        onChange: getInput(setForm, 'email'),
                        hint: 'The student receives an OTP here when claiming the existing record. Use a unique address where possible.'
                    })
                ),
                h(FormActions, null,
                    h(Link, { className: 'button button-outline', to: '/students' }, 'Cancel'),
                    h(Button, { type: 'submit', busy, disabled: catalogue.loading }, 'Save student')
                )
            )
        )
    );
}

export function StudentDetail() {
    const { id } = useParams();
    const { inform } = useAuth();
    const { value, loading, error, reload } = useResource('/students/' + id);
    const [busy, setBusy] = useState(false);
    const [actionError, setActionError] = useState('');
    const [email, setEmail] = useState('');
    const [qrVersion, setQrVersion] = useState(0);
    const student = value?.student;

    useEffect(() => {
        setEmail(student?.email || '');
    }, [student?.email]);

    async function mutate(path, body, message) {
        setBusy(true);
        setActionError('');
        try {
            const result = await api('/students/' + id + path, { method: 'POST', body });
            inform(message || result.message);
            if (path === '/rotate-qr') setQrVersion((current) => current + 1);
            reload();
            return result;
        } catch (requestError) {
            setActionError(requestError.message);
            throw requestError;
        } finally {
            setBusy(false);
        }
    }

    async function saveEmail(event) {
        event.preventDefault();
        try {
            await mutate('/email', { email }, 'Student email address updated.');
        } catch {
            // The mutation already exposes the inline error state.
        }
    }

    return group(
        h(TitleBlock, {
            eyebrow: 'STUDENT RECORD',
            title: student?.name || 'Student details',
            description: student?.matric_no || 'Review and manage the selected student record.',
            actions: h(Link, { className: 'button button-outline', to: '/students' }, 'Back to directory')
        }),
        h(Problem, { message: error || actionError }),
        loading
            ? h(Spinner)
            : student && el('div', { className: 'two-col' },
                h(Panel, null,
                    el('div', { className: 'student-heading' },
                        h(PrivatePhoto, {
                            src: student.photo_url,
                            alt: 'Student profile photograph',
                            className: 'profile-image',
                            placeholderClassName: 'profile-placeholder',
                            fallbackText: (student.name || '?').slice(0, 1)
                        }),
                        el('div', null,
                            el('h2', null, student.name),
                            h(Pill, { status: student.status }),
                            el('p', { className: 'muted' }, student.account_claimed ? 'Account claimed' : 'Account not yet claimed')
                        )
                    ),
                    el('dl', { className: 'detail-list' },
                        h(DetailRow, { label: 'Matriculation number', value: student.matric_no }),
                        h(DetailRow, { label: 'Faculty', value: student.faculty }),
                        h(DetailRow, { label: 'Department', value: student.department }),
                        h(DetailRow, { label: 'Level', value: student.level }),
                        h(DetailRow, { label: 'Email', value: student.email }),
                        h(DetailRow, { label: 'Email verified', value: student.email_verified_at ? compactDate(student.email_verified_at) : 'Not yet verified' }),
                        h(DetailRow, { label: 'Account claimed', value: student.claimed_at ? compactDate(student.claimed_at) : 'Not yet claimed' }),
                        h(DetailRow, { label: 'Created', value: compactDate(student.created_at) })
                    ),
                    el('form', { className: 'form-stack email-maintenance-form', onSubmit: saveEmail },
                        el('h3', null, 'Student email address'),
                        h(Field, {
                            label: 'Email on student record',
                            name: 'email',
                            type: 'email',
                            required: false,
                            value: email,
                            onChange: (event) => setEmail(event.target.value),
                            hint: 'The student must access this address to receive the one-time email verification code.'
                        }),
                        h(Button, { type: 'submit', busy, variant: 'outline' }, 'Save email address')
                    ),
                    h(ConfirmAction, {
                        title: (student.status === 'Active' ? 'Deactivate' : 'Activate') + ' student?',
                        text: 'This changes whether the student credential can verify as active.',
                        busy,
                        dangerous: student.status === 'Active',
                        action: () => mutate('/status', {
                            status: student.status === 'Active' ? 'Inactive' : 'Active'
                        })
                    }, student.status === 'Active' ? 'Deactivate student' : 'Activate student')
                ),
                h(Panel, null,
                    el('h2', null, 'QR credential'),
                    student.has_qr
                        ? group(
                            el('p', { className: 'muted' }, 'This QR credential is available because the student has claimed the account and completed the profile photograph.'),
                            el('img', {
                                className: 'qr-image',
                                alt: 'Student QR credential',
                                src: '/api/students/' + id + '/qr.png?v=' + qrVersion
                            }),
                            el('div', { className: 'stacked-actions' },
                                el('a', {
                                    className: 'button button-outline',
                                    href: '/api/students/' + id + '/qr.png?download=1',
                                    download: true
                                }, 'Download QR'),
                                h(ConfirmAction, {
                                    title: 'Rotate this QR credential?',
                                    text: 'The previous QR code will immediately stop working.',
                                    dangerous: true,
                                    busy,
                                    action: () => mutate('/rotate-qr', {}, 'Student QR credential refreshed.')
                                }, 'Rotate QR credential')
                            )
                        )
                        : el('div', { className: 'empty-qr-state' },
                            h(Icon, { name: 'scan-qr-code', size: 34 }),
                            el('h3', null, student.account_claimed ? 'Profile photograph required' : 'Awaiting student account claim'),
                            el('p', null, student.account_claimed
                                ? 'The student must upload a current photograph to private profile storage before a QR credential can be generated.'
                                : 'No QR credential is generated when an administrator creates or imports a student record. The student receives one after verifying the registered email and completing the profile.'),
                            !student.email && el('p', { className: 'notice' }, 'Add a valid email address to enable self-service account claiming.')
                        )
                )
            )
    );
}

export function StudentImport() {
    const { inform } = useAuth();
    const navigate = useNavigate();
    const [file, setFile] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [details, setDetails] = useState([]);

    async function submit(event) {
        event.preventDefault();
        if (!file) return;
        setBusy(true);
        setError('');
        setDetails([]);
        const form = new FormData();
        form.set('file', file);

        try {
            const result = await api('/students/import', { method: 'POST', body: form });
            inform(result.message);
            navigate('/students');
        } catch (requestError) {
            setError(requestError.message);
            setDetails(requestError.details || []);
        } finally {
            setBusy(false);
        }
    }

    return group(
        h(TitleBlock, {
            eyebrow: 'STUDENT RECORDS',
            title: 'Import student records',
            description: 'Upload a UTF-8 CSV file containing no more than 5,000 records (maximum 2 MB). The import is all-or-nothing.'
        }),
        h(Panel, { className: 'form-panel' },
            el('p', null, 'Download the template to review the required column headings and example format.'),
            el('a', { href: '/api/students/import-template', className: 'button button-outline' },
                h(Icon, { name: 'file', size: 17 }),
                'Download CSV template'
            ),
            el('form', { className: 'form-stack section-spacing', onSubmit: submit },
                h(Problem, { message: error }),
                details.length > 0 && el('ul', { className: 'error-list' },
                    ...details.map((item, index) => el('li', { key: index },
                        typeof item === 'object' ? `Row ${item.line}: ${item.message}` : item
                    ))
                ),
                h(Field, {
                    label: 'Student CSV file',
                    name: 'file',
                    type: 'file',
                    accept: '.csv,text/csv',
                    required: true,
                    onChange: (event) => setFile(event.target.files?.[0] || null),
                    hint: 'Include the email column for self-service account claiming. Each student should have a unique email address. Only import authorised institutional records.'
                }),
                h(FormActions, null,
                    h(Link, { to: '/students', className: 'button button-outline' }, 'Cancel'),
                    h(Button, { type: 'submit', busy, disabled: !file }, 'Validate and import')
                )
            )
        )
    );
}

function CameraReader({ onDetected }) {
    const [active, setActive] = useState(false);
    const [cameraId, setCameraId] = useState('');
    const [cameras, setCameras] = useState([]);
    const [message, setMessage] = useState('Camera is off.');
    const [fatal, setFatal] = useState('');
    const onDetectedRef = useRef(onDetected);

    useEffect(() => {
        onDetectedRef.current = onDetected;
    }, [onDetected]);

    useEffect(() => {
        if (!active) return undefined;

        let cancelled = false;
        let scanner = null;
        let completed = false;
        setFatal('');
        setMessage('Starting the camera…');

        async function startScanner() {
            try {
                const module = await import('html5-qrcode');
                if (cancelled) return;

                scanner = new module.Html5Qrcode('qr-reader', { verbose: false });
                const onScanSuccess = async (code) => {
                    if (completed || cancelled) return;
                    completed = true;
                    setMessage('QR code scanned. Verifying…');
                    await scanner.stop().catch(() => {});
                    if (!cancelled) {
                        setActive(false);
                        onDetectedRef.current(code.trim());
                    }
                };
                const options = {
                    fps: 12,
                    qrbox: (width, height) => ({
                        width: Math.min(250, width - 20),
                        height: Math.min(250, height - 20)
                    }),
                    aspectRatio: 1
                };
                const attempts = cameraId
                    ? [cameraId]
                    : [{ facingMode: { exact: 'environment' } }, { facingMode: 'environment' }];
                let started = false;

                for (const camera of attempts) {
                    try {
                        await scanner.start(camera, options, onScanSuccess, () => {});
                        started = true;
                        break;
                    } catch (error) {
                        if (cancelled) break;
                    }
                }

                if (!started && !cancelled) {
                    const devices = await module.Html5Qrcode.getCameras();
                    const rearCamera = devices.find((device) => /back|rear|environment/i.test(device.label)) ||
                        devices[devices.length - 1];
                    if (rearCamera) {
                        await scanner.start(rearCamera.id, options, onScanSuccess, () => {});
                        started = true;
                    }
                }

                if (cancelled) {
                    if (started) await scanner.stop().catch(() => {});
                    return;
                }

                const devices = await module.Html5Qrcode.getCameras().catch(() => []);
                setCameras(devices);
                setMessage(started
                    ? 'Camera ready. Point it at a QR code.'
                    : 'No camera is available. Use manual entry instead.');
            } catch (error) {
                if (!cancelled) {
                    setFatal('The camera could not start. Allow camera permission, choose another camera or verify manually.');
                    setMessage('Camera unavailable.');
                }
            }
        }

        startScanner();
        return () => {
            cancelled = true;
            if (scanner) {
                try {
                    Promise.resolve(scanner.stop())
                        .catch(() => {})
                        .finally(() => {
                            try {
                                scanner.clear().catch(() => {});
                            } catch (error) {
                                // The browser may already have released the camera.
                            }
                        });
                } catch (error) {
                    try {
                        scanner.clear().catch(() => {});
                    } catch (cleanupError) {
                        // No further cleanup is needed.
                    }
                }
            }
        };
    }, [active, cameraId]);

    return h(Panel, { className: 'camera-panel' },
        el('h2', null, 'Scan with your camera'),
        el('p', { className: 'muted' }, 'On a phone, StudentVerifi requests the rear-facing camera first. Your browser may ask for permission.'),
        el('div', { id: 'qr-reader', className: 'reader', 'aria-label': 'QR camera preview' }),
        el('p', { className: 'hint', role: 'status', 'aria-live': 'polite' }, message),
        h(Problem, { message: fatal }),
        cameras.length > 1 && h(Field, {
            select: true,
            name: 'camera',
            label: 'Choose camera',
            value: cameraId,
            onChange: (event) => {
                setActive(false);
                setCameraId(event.target.value);
                setMessage('Camera selected. Start the camera to use it.');
            },
            choices: cameras.map((camera, index) => ({
                value: camera.id,
                label: camera.label || `Camera ${index + 1}`
            }))
        }),
        h(Button, {
            variant: active ? 'outline' : 'primary',
            onClick: () => setActive((current) => !current)
        }, active ? 'Stop camera' : 'Start camera'),
        el('p', { className: 'hint' }, 'Camera images are processed in your browser and are not uploaded to the application.')
    );
}

export function Verify() {
    const { user } = useAuth();
    const [token, setToken] = useState('');
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const [historyFilter, setHistoryFilter] = useState('ALL');
    const [historySearch, setHistorySearch] = useState('');
    const history = useResource(user?.role === 'admin' ? '/logs' : '/verifier/activity');

    async function check(value) {
        setError('');
        setResult(null);
        if (!value.trim()) {
            setError('Enter a verification code.');
            return;
        }

        setBusy(true);
        try {
            const response = await api('/verify', {
                method: 'POST',
                body: { token: value.trim() }
            });
            setResult(response);
            history.reload();
        } catch (requestError) {
            setError(requestError.message);
            history.reload();
        } finally {
            setBusy(false);
        }
    }

    async function onScan(code) {
        setToken(code);
        await check(code);
    }

    const historyItems = Array.isArray(history.value?.items) ? history.value.items : [];
    const historyCounts = historyItems.reduce((counts, item) => {
        const outcome = String(item.result || '').toUpperCase();
        counts[outcome] = (counts[outcome] || 0) + 1;
        return counts;
    }, {});
    const searchTerm = historySearch.trim().toLowerCase();
    const visibleHistory = historyItems.filter((item) => {
        const outcome = String(item.result || '').toUpperCase();
        const matchesFilter = historyFilter === 'ALL' || outcome === historyFilter;
        const searchable = [item.student_name, item.matric_no, item.department, item.verified_by_name]
            .filter(Boolean)
            .join(' ')
            .toLowerCase();
        return matchesFilter && (!searchTerm || searchable.includes(searchTerm));
    });

    return group(
        h(TitleBlock, {
            eyebrow: 'IDENTITY VERIFICATION',
            title: 'Verification centre',
            description: 'Scan or enter a QR credential, review the result and consult recent verification activity in one workspace.'
        }),
        h(Problem, { message: error }),
        el('div', { className: 'two-col verification-workspace' },
            h(CameraReader, { onDetected: onScan }),
            h(Panel, null,
                el('h2', null, 'Enter verification code'),
                el('p', { className: 'muted' }, 'Use manual entry if your camera is unavailable or you have a code to check.'),
                el('form', {
                    onSubmit: (event) => {
                        event.preventDefault();
                        check(token);
                    },
                    className: 'form-stack'
                },
                    h(Field, {
                        label: 'Verification code',
                        name: 'token',
                        value: token,
                        onChange: getInput(setToken, 'value'),
                        autoComplete: 'off',
                        required: true,
                        placeholder: 'Enter or paste code here'
                    }),
                    h(Button, { type: 'submit', busy }, 'Verify identity')
                ),
                result && el('div', {
                    className: 'verification-result',
                    role: 'status',
                    'aria-live': 'polite'
                },
                    el('div', { className: 'result-head' },
                        el('h3', null, 'Verification result'),
                        h(Pill, { status: result.outcome })
                    ),
                    el('p', null, result.message),
                    result.student && el('div', { className: 'result-student' },
                        h(PrivatePhoto, {
                            src: result.student.photo_url,
                            alt: 'Student record photograph',
                            className: 'profile-image',
                            placeholderClassName: 'profile-placeholder',
                            fallbackText: (result.student.name || '?').slice(0, 1)
                        }),
                        el('div', null,
                            el('strong', null, result.student.name),
                            el('p', null, result.student.matric_no),
                            el('p', null, `${result.student.department} · ${result.student.level} level`),
                            user?.role === 'admin' && h(Link, {
                                to: '/students/' + result.student.id,
                                className: 'text-link'
                            }, 'View student record')
                        )
                    ),
                    el('p', { className: 'notice' }, 'Check the person’s identity independently. A copied QR code is not proof that its holder is the student.')
                )
            )
        ),
        h(Panel, { className: 'verification-history-panel' },
            el('div', { className: 'panel-heading-row' },
                el('div', null,
                    el('p', { className: 'eyebrow' }, 'VERIFIED ACTIVITY'),
                    el('h2', null, 'Verification history'),
                    el('p', { className: 'muted' }, user?.role === 'admin' ? 'The latest 250 verification outcomes across administrators, verifiers and public visitors. Reusable QR tokens are never displayed.' : 'Your own recent verification outcomes. Reusable QR tokens are never displayed.')
                ),
                h(Button, {
                    variant: 'outline',
                    onClick: history.reload,
                    disabled: history.loading
                }, history.loading ? 'Refreshing…' : 'Refresh history')
            ),
            h(Problem, { message: history.error }),
            el('div', { className: 'verification-history-summary' },
                ...[
                    ['ALL', 'All checks', historyItems.length],
                    ['VALID', 'Valid', historyCounts.VALID || 0],
                    ['INACTIVE', 'Inactive', historyCounts.INACTIVE || 0],
                    ['INVALID', 'Invalid', historyCounts.INVALID || 0],
                    ['INCOMPLETE', 'Profile incomplete', historyCounts.INCOMPLETE || 0]
                ].map(([key, label, count]) => el('div', {
                    className: 'verification-summary-item',
                    key
                },
                    el('span', null, label),
                    el('strong', null, Number(count).toLocaleString())
                ))
            ),
            el('div', { className: 'verification-history-toolbar' },
                el('div', { className: 'verification-history-filters', role: 'group', 'aria-label': 'Filter verification outcomes' },
                    ...[
                        ['ALL', 'All'],
                        ['VALID', 'Valid'],
                        ['INACTIVE', 'Inactive'],
                        ['INVALID', 'Invalid'],
                        ['INCOMPLETE', 'Incomplete']
                    ].map(([key, label]) => h(Button, {
                        key,
                        variant: historyFilter === key ? 'primary' : 'outline',
                        'aria-pressed': historyFilter === key,
                        onClick: () => setHistoryFilter(key)
                    }, label))
                ),
                h(Field, {
                    label: 'Search activity',
                    name: 'verification-search',
                    type: 'search',
                    placeholder: 'Student, matric no. or verifier',
                    value: historySearch,
                    onChange: getInput(setHistorySearch, 'value')
                })
            ),
            history.loading
                ? h(Spinner, { label: 'Loading verification history…' })
                : visibleHistory.length
                    ? el('div', { className: 'table-scroll' },
                        el('table', null,
                            el('thead', null,
                                el('tr', null,
                                    ...['Outcome', 'Student', 'Matriculation number', 'Verifier', 'Source', 'Date and time'].map((heading) =>
                                        el('th', { key: heading, scope: 'col' }, heading)
                                    )
                                )
                            ),
                            el('tbody', null,
                                ...visibleHistory.map((item) => el('tr', { key: item.id },
                                    el('td', null, h(Pill, { status: item.result })),
                                    el('td', null, item.student_name || 'Unmatched / unavailable record'),
                                    el('td', null, item.matric_no || '—'),
                                    el('td', null, item.verified_by_name || 'Former account'),
                                    el('td', null, item.channel === 'public' ? 'Public' : item.channel === 'verifier' ? 'Verifier' : 'Staff'),
                                    el('td', null, compactDate(item.verified_at))
                                ))
                            )
                        )
                    )
                    : h(Empty, {
                        title: historyItems.length ? 'No matching verification events' : 'No verification activity yet',
                        text: historyItems.length
                            ? 'Change the outcome filter or search term to see other events.'
                            : 'New checks will appear here after an authorised verifier scans or enters a credential.'
                    })
        )
    );
}

export function Requests() {
    const { inform } = useAuth();
    const { value, loading, error, reload } = useResource('/registration-requests');
    const [busy, setBusy] = useState(0);
    const [actionError, setActionError] = useState('');
    const [filter, setFilter] = useState('All');
    const [search, setSearch] = useState('');

    async function decide(id, choice) {
        setBusy(id);
        setActionError('');
        try {
            const response = await api('/registration-requests/' + id + '/' + choice, {
                method: 'POST',
                body: {}
            });
            inform(response.message);
            reload();
        } catch (requestError) {
            setActionError(requestError.message);
        } finally {
            setBusy(0);
        }
    }

    const items = Array.isArray(value?.items) ? value.items : [];
    const counts = items.reduce((summary, item) => {
        const status = String(item.status || 'Pending');
        summary[status] = (summary[status] || 0) + 1;
        return summary;
    }, { Pending: 0, Approved: 0, Rejected: 0 });
    const searchTerm = search.trim().toLowerCase();
    const visibleItems = items.filter((item) => {
        const statusMatches = filter === 'All' || item.status === filter;
        const searchable = [item.name, item.matric_no, item.faculty, item.department, item.level]
            .filter(Boolean)
            .join(' ')
            .toLowerCase();
        return statusMatches && (!searchTerm || searchable.includes(searchTerm));
    });

    return group(
        h(TitleBlock, {
            eyebrow: 'ACCOUNT ACCESS',
            title: 'Historical account requests',
            description: 'Review historical claim-code requests created before automated email-based account claiming was introduced. New student claims are activated automatically after email verification and profile completion.',
            actions: h(Button, {
                variant: 'outline',
                onClick: reload,
                disabled: loading
            }, loading ? 'Refreshing…' : 'Refresh requests')
        }),
        h(Problem, { message: error || actionError }),
        el('section', { className: 'stats-grid request-stats-grid', 'aria-label': 'Registration request totals' },
            h(Stat, { value: items.length.toLocaleString(), label: 'All requests', icon: 'requests', tone: 'blue', note: 'Request history' }),
            h(Stat, { value: counts.Pending.toLocaleString(), label: 'Pending', icon: 'history', tone: 'amber', note: 'Awaiting review' }),
            h(Stat, { value: counts.Approved.toLocaleString(), label: 'Approved', icon: 'check', tone: 'green', note: 'Access granted' }),
            h(Stat, { value: counts.Rejected.toLocaleString(), label: 'Rejected', icon: 'close', tone: 'violet', note: 'Access declined' })
        ),
        el('div', { className: 'request-history-toolbar' },
            el('div', { className: 'request-filter-tabs', role: 'group', 'aria-label': 'Filter account requests' },
                ...[
                    ['All', 'All'],
                    ['Pending', 'Pending'],
                    ['Approved', 'Approved'],
                    ['Rejected', 'Rejected']
                ].map(([key, label]) => h(Button, {
                    key,
                    variant: filter === key ? 'primary' : 'outline',
                    'aria-pressed': filter === key,
                    onClick: () => setFilter(key)
                }, `${label} (${key === 'All' ? items.length : counts[key]})`))
            ),
            h(Field, {
                label: 'Search requests',
                name: 'request-search',
                type: 'search',
                placeholder: 'Student name or matriculation number',
                value: search,
                onChange: getInput(setSearch, 'value')
            })
        ),
        loading
            ? h(Spinner, { label: 'Loading registration requests…' })
            : visibleItems.length
                ? el('div', { className: 'cards-list request-history-list' },
                    ...visibleItems.map((item) => h(Panel, { key: item.id, className: 'request-history-card' },
                        el('div', { className: 'request-row' },
                            el('div', { className: 'request-identity' },
                                el('div', { className: 'request-title-line' },
                                    el('h2', null, item.name || 'Student record'),
                                    h(Pill, { status: item.status })
                                ),
                                el('p', { className: 'request-matric' }, item.matric_no || 'No matriculation number'),
                                el('p', { className: 'request-academic' }, [item.faculty, item.department, item.level].filter(Boolean).join(' · ') || 'Academic details unavailable'),
                                el('p', { className: 'hint' }, 'Requested ' + compactDate(item.requested_at)),
                                el('p', { className: 'request-claim-status' }, item.claim_code_verified
                                    ? 'One-time claim code verified'
                                    : 'Claim-code verification not recorded')
                            ),
                            item.status === 'Pending'
                                ? el('div', { className: 'actions request-actions' },
                                    h(ConfirmAction, {
                                        title: 'Reject this account request?',
                                        text: `This will reject the legacy account request for ${item.matric_no}. The student will need to contact the administrator to resolve the record before using the new self-service claim process.`,
                                        dangerous: true,
                                        busy: busy === item.id,
                                        action: () => decide(item.id, 'reject')
                                    }, 'Reject'),
                                    h(ConfirmAction, {
                                        title: 'Approve student account?',
                                        text: `You are about to grant account access for ${item.matric_no}. Confirm that this request is authorised.`,
                                        busy: busy === item.id,
                                        action: () => decide(item.id, 'approve')
                                    }, 'Approve')
                                )
                                : el('div', { className: 'request-review-meta' },
                                    el('strong', null, item.status === 'Approved' ? 'Access approved' : 'Request rejected'),
                                    el('span', null, 'Decision recorded by ' + (item.reviewed_by_name || 'System')),
                                    el('span', null, compactDate(item.reviewed_at))
                                )
                        )
                    ))
                )
                : h(Empty, {
                    title: filter === 'Pending' ? 'No pending requests' : `No ${filter.toLowerCase()} requests`,
                    text: searchTerm
                        ? 'No requests match the current search. Clear the search term or choose another status.'
                        : filter === 'All'
                            ? 'New student claims are activated automatically after email verification and profile completion. This page retains older claim-code request history.'
                            : 'There are no requests in this status.'
                })
    );
}

export function AdminAudit() {
    const { value, loading, error, reload } = useResource('/admin-audit');
    const items = Array.isArray(value?.items) ? value.items : [];

    return group(
        h(TitleBlock, {
            eyebrow: 'ACCOUNTABILITY',
            title: 'Administrative activity',
            description: 'A record of important administrative changes, account decisions and security-related actions.',
            actions: h(Button, {
                variant: 'outline',
                onClick: reload,
                disabled: loading
            }, loading ? 'Refreshing…' : 'Refresh activity')
        }),
        h(Problem, { message: error }),
        loading
            ? h(Spinner, { label: 'Loading administrative activity…' })
            : items.length
                ? h(Panel, null,
                    el('div', { className: 'table-scroll' },
                        el('table', null,
                            el('thead', null,
                                el('tr', null,
                                    ...['Date and time', 'Actor', 'Action', 'Target', 'Summary'].map((heading) =>
                                        el('th', { key: heading, scope: 'col' }, heading)
                                    )
                                )
                            ),
                            el('tbody', null,
                                ...items.map((item, index) => el('tr', { key: item.id || index },
                                    el('td', null, compactDate(item.created_at)),
                                    el('td', null, item.actor || 'Former account'),
                                    el('td', null, el('strong', null, String(item.event || 'Activity').replaceAll('_', ' ').replaceAll('.', ' '))),
                                    el('td', null, item.target_type
                                        ? `${item.target_type}${item.target_id ? ' #' + item.target_id : ''}`
                                        : '—'),
                                    el('td', null, item.details || '—')
                                ))
                            )
                        )
                    )
                )
                : h(Empty, {
                    title: 'No administrative activity yet',
                    text: 'Account decisions and administrative actions will appear here when recorded.'
                })
    );
}

export function StudentAccount() {
    const { value, loading, error, reload } = useResource('/student/me');
    const { inform } = useAuth();
    const [photo, setPhoto] = useState(null);
    const [preview, setPreview] = useState('');
    const [busy, setBusy] = useState(false);
    const [photoError, setPhotoError] = useState('');
    const student = value?.student;

    useEffect(() => {
        if (!photo) {
            setPreview('');
            return undefined;
        }
        const url = URL.createObjectURL(photo);
        setPreview(url);
        return () => URL.revokeObjectURL(url);
    }, [photo]);

    async function uploadPhoto(event) {
        event.preventDefault();
        setPhotoError('');
        if (!photo) {
            setPhotoError('Choose a profile photograph first.');
            return;
        }
        const payload = new FormData();
        payload.append('photo', photo);
        setBusy(true);
        try {
            const result = await api('/student/profile-photo', { method: 'POST', body: payload });
            inform(result.message);
            setPhoto(null);
            reload();
        } catch (requestError) {
            setPhotoError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    return group(
        h(TitleBlock, {
            eyebrow: 'STUDENT SPACE',
            title: 'My student card',
            description: 'Manage your profile photograph and access your QR credential.',
            actions: h(Link, { className: 'button button-outline', to: '/account/password' }, 'Change password')
        }),
        h(Problem, { message: error || photoError }),
        loading
            ? h(Spinner)
            : student && el('div', { className: 'two-col' },
                h(Panel, null,
                    el('div', { className: 'student-heading' },
                        h(PrivatePhoto, {
                            src: student.photo_url,
                            alt: 'Your profile photograph',
                            className: 'profile-image',
                            placeholderClassName: 'profile-placeholder',
                            fallbackText: (student.name || '?').slice(0, 1)
                        }),
                        el('div', null,
                            el('h2', null, student.name),
                            h(Pill, { status: student.status }),
                            el('p', { className: 'muted' }, student.photo_private ? 'Student-submitted photograph stored securely' : student.photo_available ? 'Existing photograph found; upload a new copy to enable QR verification' : 'Profile photograph required')
                        )
                    ),
                    el('dl', { className: 'detail-list' },
                        h(DetailRow, { label: 'Matriculation number', value: student.matric_no }),
                        h(DetailRow, { label: 'Faculty', value: student.faculty }),
                        h(DetailRow, { label: 'Department', value: student.department }),
                        h(DetailRow, { label: 'Level', value: student.level })
                    ),
                    el('form', { className: 'form-stack photo-update-form', onSubmit: uploadPhoto },
                        el('h3', null, student.photo_private ? 'Update profile photograph' : 'Upload a profile photograph to enable QR verification'),
                        el('label', { className: 'photo-upload-field' },
                            el('span', { className: 'photo-upload-preview' },
                                preview
                                    ? el('img', { src: preview, alt: 'New photograph preview' })
                                    : h(Icon, { name: 'camera', size: 28 })
                            ),
                            el('strong', null, photo ? photo.name : 'Choose a photograph'),
                            el('small', null, 'JPEG, PNG or WebP · Maximum 2 MB'),
                            el('input', {
                                type: 'file',
                                accept: 'image/jpeg,image/png,image/webp',
                                required: true,
                                onChange: (event) => setPhoto(event.target.files?.[0] || null)
                            })
                        ),
                        h(Button, { type: 'submit', busy, disabled: !photo }, student.photo_available ? 'Update photograph' : 'Save photograph')
                    )
                ),
                h(Panel, null,
                    el('h2', null, 'My QR credential'),
                    student.has_qr
                        ? group(
                            el('img', {
                                src: '/api/student/my-qr.png',
                                alt: 'Your unique student QR credential',
                                className: 'qr-image'
                            }),
                            el('a', {
                                href: '/api/student/my-qr.png?download=1',
                                className: 'button button-primary',
                                download: true
                            }, 'Download my QR code'),
                            el('p', { className: 'hint' }, 'Your QR code opens a limited public verification page. Protect it and present it with your student identity evidence.')
                        )
                        : el('div', { className: 'empty-qr-state' },
                            h(Icon, { name: 'scan-qr-code', size: 34 }),
                            el('h3', null, 'QR credential not yet available'),
                            el('p', null, 'Your QR credential is generated only after your account is activated and a current profile photograph is stored privately.')
                        )
                )
            )
    );
}

export function Password() {
    const [form, setForm] = useState({
        current_password: '',
        new_password: '',
        confirm: ''
    });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    async function submit(event) {
        event.preventDefault();
        setError('');
        setSuccess('');
        if (form.new_password !== form.confirm) {
            setError('The passwords do not match.');
            return;
        }
        setBusy(true);
        try {
            const result = await api('/account/password', { method: 'POST', body: form });
            setSuccess(result.message);
            setForm({ current_password: '', new_password: '', confirm: '' });
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    return group(
        h(TitleBlock, {
            eyebrow: 'ACCOUNT SECURITY',
            title: 'Change password',
            description: 'Use a strong, unique password containing at least 12 characters.'
        }),
        h(Panel, { className: 'form-panel' },
            el('form', { onSubmit: submit, className: 'form-stack' },
                h(Problem, { message: error }),
                success && el('p', { className: 'alert alert-success', role: 'status' }, success),
                h(Field, {
                    label: 'Current password',
                    name: 'current_password',
                    type: 'password',
                    autoComplete: 'current-password',
                    required: true,
                    value: form.current_password,
                    onChange: getInput(setForm, 'current_password')
                }),
                h(Field, {
                    label: 'New password',
                    name: 'new_password',
                    type: 'password',
                    required: true,
                    minLength: 12,
                    maxLength: 128,
                    autoComplete: 'new-password',
                    value: form.new_password,
                    onChange: getInput(setForm, 'new_password')
                }),
                h(Field, {
                    label: 'Confirm new password',
                    name: 'confirm',
                    type: 'password',
                    required: true,
                    autoComplete: 'new-password',
                    value: form.confirm,
                    onChange: getInput(setForm, 'confirm')
                }),
                h(Button, { type: 'submit', busy }, 'Update password')
            )
        )
    );
}

export function Cleanup() {
    const { value, loading, error, reload } = useResource('/students/demo-cleanup');
    const { inform } = useAuth();
    const [confirmation, setConfirmation] = useState('');
    const [busy, setBusy] = useState(false);
    const [actionError, setActionError] = useState('');

    async function remove(event) {
        event.preventDefault();
        setBusy(true);
        setActionError('');
        try {
            const result = await api('/students/demo-cleanup', {
                method: 'POST',
                body: { confirmation }
            });
            inform(result.message);
            setConfirmation('');
            reload();
        } catch (requestError) {
            setActionError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    return group(
        h(TitleBlock, {
            eyebrow: 'MAINTENANCE',
            title: 'Remove synthetic test records',
            description: 'Review and remove only records matching the exact known DEMO/2026 test matriculation-number pattern.'
        }),
        h(Panel, { className: 'form-panel' },
            h(Problem, { message: error || actionError }),
            loading
                ? h(Spinner)
                : group(
                    el('p', null,
                        el('strong', null, (value?.count ?? '—') + ' matching synthetic records'),
                        ' are selected for removal. Other student records are not selected.'
                    ),
                    el('p', { className: 'notice' }, 'Deletion cannot be undone. Associated accounts and requests will be removed. Verification history will be retained without links to deleted students.'),
                    el('form', { onSubmit: remove, className: 'form-stack' },
                        h(Field, {
                            label: 'Type DELETE DEMO RECORDS to confirm',
                            name: 'confirmation',
                            value: confirmation,
                            onChange: getInput(setConfirmation, 'value'),
                            required: true,
                            autoComplete: 'off'
                        }),
                        h(Button, {
                            type: 'submit',
                            variant: 'danger',
                            busy,
                            disabled: value?.count === 0 || confirmation !== 'DELETE DEMO RECORDS'
                        }, 'Delete matching test records')
                    )
                )
        )
    );
}

export function PublicCredential() {
    const location = useLocation();
    const { token: pathToken } = useParams();
    const token = location.hash.replace(/^#/, '').trim() || pathToken || '';
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        if (!token) {
            setResult(null);
            setError('This verification link is incomplete. Scan a valid StudentVerifi QR code.');
            setLoading(false);
            return undefined;
        }
        const controller = new AbortController();
        setLoading(true);
        setError('');
        api('/public/verify', {
            method: 'POST',
            body: { token },
            signal: controller.signal
        })
            .then(setResult)
            .catch((requestError) => {
                if (requestError.name !== 'AbortError') setError(requestError.message);
            })
            .finally(() => {
                if (!controller.signal.aborted) setLoading(false);
            });
        return () => controller.abort();
    }, [token]);

    return el('section', { className: 'public-credential-page' },
        el('div', { className: 'public-credential-heading' },
            el('p', { className: 'eyebrow' }, 'STUDENTVERIFI PUBLIC CHECK'),
            el('h1', null, 'Student credential verification'),
            el('p', { className: 'lead' }, 'This page displays only the limited information needed for a basic credential check.')
        ),
        h(Panel, { className: 'public-credential-card' },
            loading
                ? h(Spinner, { label: 'Checking the student credential…' })
                : error
                    ? h(Problem, { message: error })
                    : result && group(
                        el('div', { className: 'public-credential-result' },
                            h(Pill, { status: result.outcome }),
                            el('h2', null, result.outcome === 'VALID' ? 'Credential is valid' : result.outcome === 'INACTIVE' ? 'Student record is inactive' : result.outcome === 'INCOMPLETE' ? 'Profile is incomplete' : 'Credential not recognised'),
                            el('p', null, result.message)
                        ),
                        result.student && el('div', { className: 'public-credential-student' },
                            result.student.photo_data
                                ? el('img', { src: result.student.photo_data, alt: 'Student profile photograph', className: 'public-credential-photo' })
                                : el('div', { className: 'public-credential-photo-placeholder' }, h(Icon, { name: 'user', size: 34 })),
                            el('div', null,
                                el('p', { className: 'eyebrow' }, result.student.institution),
                                el('h2', null, result.student.name),
                                el('p', null, 'Matriculation number: ' + result.student.matric_no_masked),
                                el('p', null, 'Record status: ' + result.student.status)
                            )
                        ),
                        el('p', { className: 'notice' }, 'A valid QR credential confirms a matching student record. The photograph is student-submitted and is not independently authenticated by facial recognition. It does not prove that the person presenting the code is the student. Compare the photograph with the person and request appropriate identification when necessary.'),
                        el('p', { className: 'prototype-disclaimer' }, 'StudentVerifi is an academic software prototype and is not an official institutional verification service unless formally authorised by the institution.')
                    )
        ),
        h(Link, { to: '/', className: 'text-link' }, 'Return to StudentVerifi')
    );
}

export function VerifierAccept() {
    const location = useLocation();
    const navigate = useNavigate();
    const { setUser, inform } = useAuth();
    const token = new URLSearchParams(location.search).get('token') || location.hash.replace(/^#/, '').trim();
    const [form, setForm] = useState({ password: '', confirm: '' });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    async function submit(event) {
        event.preventDefault();
        setError('');
        if (!token) {
            setError('The invitation link is incomplete. Ask the administrator to send a new invitation.');
            return;
        }
        if (form.password !== form.confirm) {
            setError('The passwords do not match.');
            return;
        }
        setBusy(true);
        try {
            const result = await api('/verifier-invitations/accept', {
                method: 'POST',
                body: { token, password: form.password, confirm: form.confirm }
            });
            setUser(result.user);
            inform(result.message);
            navigate('/verify', { replace: true });
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    return el('div', { className: 'auth-layout verifier-invite-layout' },
        el('section', { className: 'auth-intro' },
            el('p', { className: 'eyebrow' }, 'AUTHORISED VERIFIER'),
            el('h1', null, 'Set up your verification account.'),
            el('p', { className: 'lead' }, 'Create a password to activate the verifier access granted by the StudentVerifi administrator.'),
            el('div', { className: 'registration-note' },
                h(Icon, { name: 'shield-check', size: 18 }),
                el('p', null, 'Verifier accounts can check student credentials but cannot manage student records or access administrator functions.')
            )
        ),
        h(Panel, { className: 'auth-panel' },
            el('form', { className: 'form-stack', onSubmit: submit },
                el('div', { className: 'auth-panel-heading' },
                    el('p', { className: 'eyebrow' }, 'INVITATION ACCEPTANCE'),
                    el('h2', null, 'Create your password'),
                    el('p', null, 'This invitation can be used once and expires after 48 hours.')
                ),
                h(Problem, { message: error }),
                h(Field, {
                    label: 'Password', name: 'password', type: 'password', required: true,
                    minLength: 12, maxLength: 128, autoComplete: 'new-password',
                    value: form.password, onChange: getInput(setForm, 'password')
                }),
                h(Field, {
                    label: 'Confirm password', name: 'confirm', type: 'password', required: true,
                    minLength: 12, maxLength: 128, autoComplete: 'new-password',
                    value: form.confirm, onChange: getInput(setForm, 'confirm')
                }),
                h(Button, { type: 'submit', busy, className: 'button-full', disabled: !token }, 'Activate verifier account')
            )
        )
    );
}

export function VerifierManagement() {
    const { inform } = useAuth();
    const { value, loading, error, reload } = useResource('/verifiers');
    const [form, setForm] = useState({ display_name: '', email: '' });
    const [busy, setBusy] = useState(false);
    const [actionError, setActionError] = useState('');
    const [busyId, setBusyId] = useState(0);

    async function invite(event) {
        event.preventDefault();
        setBusy(true);
        setActionError('');
        try {
            const result = await api('/verifiers', { method: 'POST', body: form });
            inform(result.message);
            setForm({ display_name: '', email: '' });
            reload();
        } catch (requestError) {
            setActionError(requestError.message);
            reload();
        } finally {
            setBusy(false);
        }
    }

    async function changeStatus(item, isActive) {
        setBusyId(item.id);
        setActionError('');
        try {
            const result = await api('/verifiers/' + item.id + '/status', {
                method: 'POST',
                body: { is_active: isActive }
            });
            inform(result.message);
            reload();
        } catch (requestError) {
            setActionError(requestError.message);
        } finally {
            setBusyId(0);
        }
    }

    async function resend(item) {
        setBusyId(item.id);
        setActionError('');
        try {
            const result = await api('/verifiers/' + item.id + '/invite', { method: 'POST', body: {} });
            inform(result.message);
            reload();
        } catch (requestError) {
            setActionError(requestError.message);
        } finally {
            setBusyId(0);
        }
    }

    const items = value?.items || [];
    return group(
        h(TitleBlock, {
            eyebrow: 'ACCESS MANAGEMENT',
            title: 'Verifier accounts',
            description: 'Invite lecturers and authorised staff to verify student credentials without giving them administrator permissions.'
        }),
        h(Problem, { message: error || actionError }),
        h(Panel, { className: 'form-panel' },
            el('h2', null, 'Invite a verifier'),
            el('form', { className: 'form-stack', onSubmit: invite },
                el('div', { className: 'form-grid' },
                    h(Field, {
                        label: 'Staff member’s name', name: 'display_name', required: true,
                        value: form.display_name, onChange: getInput(setForm, 'display_name')
                    }),
                    h(Field, {
                        label: 'Staff email address', name: 'email', type: 'email', required: true,
                        value: form.email, onChange: getInput(setForm, 'email')
                    })
                ),
                h(Button, { type: 'submit', busy }, 'Send verifier invitation')
            )
        ),
        h(Panel, null,
            el('div', { className: 'panel-heading-row' },
                el('div', null,
                    el('p', { className: 'eyebrow' }, 'VERIFIER DIRECTORY'),
                    el('h2', null, 'Invited and active verifiers'),
                    el('p', { className: 'muted' }, 'Verifier accounts can scan and verify credentials only. They cannot access student administration.')
                ),
                h(Button, { variant: 'outline', onClick: reload, disabled: loading }, 'Refresh')
            ),
            loading
                ? h(Spinner)
                : items.length
                    ? el('div', { className: 'table-scroll' },
                        el('table', null,
                            el('thead', null,
                                el('tr', null, ...['Verifier', 'Email', 'Access', 'Last sign-in', 'Actions'].map((heading) => el('th', { key: heading, scope: 'col' }, heading)))
                            ),
                            el('tbody', null,
                                ...items.map((item) => {
                                    const accepted = Boolean(item.accepted_at);
                                    const state = item.is_active ? 'Active' : accepted ? 'Suspended' : 'Invitation pending';
                                    return el('tr', { key: item.id },
                                        el('td', null, item.display_name || 'Verifier'),
                                        el('td', null, item.email),
                                        el('td', null, h(Pill, { status: state })),
                                        el('td', null, compactDate(item.last_login_at)),
                                        el('td', null,
                                            el('div', { className: 'table-actions' },
                                                !accepted && h(Button, { className: 'button-small', variant: 'outline', busy: busyId === item.id, onClick: () => resend(item) }, 'Resend invite'),
                                                accepted && h(Button, { className: 'button-small', variant: 'outline', busy: busyId === item.id, onClick: () => changeStatus(item, !item.is_active) }, item.is_active ? 'Suspend' : 'Reactivate')
                                            )
                                        )
                                    );
                                })
                            )
                        )
                    )
                    : h(Empty, { title: 'No verifiers invited yet', text: 'Invite lecturers or authorised staff members to verify student credentials.' })
        )
    );
}

export function VerifierActivity() {
    const { value, loading, error, reload } = useResource('/verifier/activity');
    const items = value?.items || [];
    return group(
        h(TitleBlock, {
            eyebrow: 'VERIFIER WORKSPACE',
            title: 'My verification activity',
            description: 'Review the student credential checks performed through your verifier account.'
        }),
        h(Problem, { message: error }),
        h(Panel, null,
            el('div', { className: 'panel-heading-row' },
                el('div', null, el('h2', null, 'Recent checks'), el('p', { className: 'muted' }, 'Only your own verification activity is shown here.')),
                h(Button, { variant: 'outline', onClick: reload, disabled: loading }, 'Refresh')
            ),
            loading
                ? h(Spinner)
                : items.length
                    ? el('div', { className: 'table-scroll' },
                        el('table', null,
                            el('thead', null, el('tr', null, ...['Outcome', 'Student', 'Matriculation number', 'Date and time'].map((heading) => el('th', { key: heading, scope: 'col' }, heading)))),
                            el('tbody', null, ...items.map((item) => el('tr', { key: item.id },
                                el('td', null, h(Pill, { status: item.result })),
                                el('td', null, item.student_name || 'Unavailable record'),
                                el('td', null, item.matric_no || '—'),
                                el('td', null, compactDate(item.verified_at))
                            )))
                        )
                    )
                    : h(Empty, { title: 'No verification activity yet', text: 'Your completed student checks will appear here.' })
        )
    );
}

export function Missing() {
    return el('div', { className: 'center-block' },
        el('span', { className: 'access-icon' }, h(Icon, { name: 'file', size: 26 })),
        el('h1', null, 'Page not found'),
        el('p', null, 'The page you requested does not exist or may have moved.'),
        h(Link, { to: '/', className: 'button button-primary' }, 'Return to homepage')
    );
}
