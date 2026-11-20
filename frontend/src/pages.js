import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, compactDate } from './api.js';
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
        ['requests', 'Controlled student access', 'Students request access with a private one-time code. An administrator reviews each request before approval.'],
        ['history', 'Accountable activity', 'Verification outcomes and important administrative actions are recorded for later review.']
    ];
    const steps = [
        ['01', 'Register the student', 'An authorised administrator adds a student record or imports a validated register.'],
        ['02', 'Issue a private code', 'The administrator gives the correct student a one-time claim code to request account access.'],
        ['03', 'Review account access', 'The student submits matching details. An administrator reviews the request before approving it.'],
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
                    ['requests', 'Reviewed account requests', 'Student accounts remain subject to administrator approval.'],
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
                el('p', null, 'Administrators and authorised verifiers can sign in. Students can request access using a private claim code issued by an administrator.')
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
            ['shield', '2. Issue a private claim code', 'When a student needs an account, an administrator issues a one-time code from the student record and shares it privately.'],
            ['requests', '3. Submit and review account access', 'The student enters matching details and a password. The administrator reviews the request before approval.'],
            ['verify', '4. Scan or enter a QR credential', 'An authorised verifier scans a QR credential using a phone camera or enters the code manually.'],
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
            ['students', 'Who uses it', 'Administrators manage records and account requests. Authorised verifiers use the scanning interface. Students with approved accounts can access their own student card and QR credential.'],
            ['shield', 'How access is controlled', 'The application separates administrator and student functions. Student access requests require a private one-time claim code and administrator approval.'],
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
            ['shield', 'Protect credentials', 'Passwords, private claim codes and QR credentials should not be shared publicly. Administrators should rotate credentials if they are compromised.'],
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
            ['user', 'Student account access', 'Ask the administrator to confirm that your record is present and issue a private one-time claim code. If you have already submitted a request, wait for the review.'],
            ['book', 'Student record correction', 'If your name, matriculation number, faculty, department or level is incorrect, ask an authorised administrator to check the source register.'],
            ['verify', 'QR and camera support', 'Allow camera access in your browser, select the rear camera where available and use manual entry if scanning is unavailable.'],
            ['shield', 'Security concerns', 'Report a lost QR credential, suspected account access or incorrect verification outcome promptly. Never include a password or claim code in a support message.']
        ],
        notice: 'No public support email or telephone number has been configured in this prototype. Use the institution’s approved support channel.'
    }
};

const faqItems = [
    ['Can any student create an account?', 'No. The student must already have a record in the register, receive a private one-time claim code from an administrator and submit matching details. An administrator must approve the request before the account is activated.'],
    ['What if I do not have a claim code?', 'Contact the administrator responsible for StudentVerifi. The administrator can issue a private code from your existing student record.'],
    ['Why does the form say an account request is already pending?', 'A request for that student record has already been submitted and is awaiting administrator review. Do not submit another request. Contact the administrator if the request has been pending longer than expected.'],
    ['What if I already have an account?', 'Use the sign-in page with your matriculation number or account username and password. If you cannot access the account, contact the administrator.'],
    ['Why does my QR code not verify?', 'The student record may be inactive, the credential may have been rotated, or the code may not match a current record. Ask an authorised administrator to review it.'],
    ['Does scanning a valid QR code prove the holder is the student?', 'No. A QR scan checks the credential against the student register. The verifier must independently compare the person with approved identification or another reliable identity source.'],
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
                el('p', null, 'For a question about a specific student record or account, contact the administrator for your installation. Do not share passwords or private claim codes.')
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
            navigate(result.role === 'admin' ? '/dashboard' : '/student/account', { replace: true });
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
            el('p', { className: 'lead' }, 'Sign in to continue to the student register, identity verification tools or your student card.'),
            el('div', { className: 'auth-benefits' },
                ...[
                    ['shield', 'Protected access', 'Your account role determines which workspace tools are available.'],
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
                    el('p', null, 'Signed in as ' + user.username + '.'),
                    h(Link, {
                        to: user.role === 'admin' ? '/dashboard' : '/student/account',
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
                        el('p', null, 'Use your administrator username or student matriculation number.')
                    ),
                    h(Problem, { message: error }),
                    h(Field, {
                        label: 'Username or matriculation number',
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
                    el('p', { className: 'form-note' }, 'Student without an account? ', h(InlineLink, { to: '/register' }, 'Request access'))
                )
        )
    );
}

export function Register() {
    const initial = {
        matric_no: '', first_name: '', middle_name: '', last_name: '',
        faculty: '', department: '', level: '', claim_code: '', password: '', confirm: ''
    };
    const [form, setForm] = useState(initial);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [busy, setBusy] = useState(false);
    const catalogue = useResource('/catalogue');
    const departmentChoices = catalogue.value?.faculty_departments?.[form.faculty] || [];

    async function submit(event) {
        event.preventDefault();
        setError('');
        setSuccess('');
        if (form.password !== form.confirm) {
            setError('The passwords do not match.');
            return;
        }
        if (!catalogue.value) {
            setError('The student catalogue is still loading. Please wait and try again.');
            return;
        }

        setBusy(true);
        try {
            const result = await api('/register', { method: 'POST', body: form });
            setSuccess(result.message);
            setForm(initial);
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    return el('div', { className: 'registration-layout' },
        el('section', { className: 'registration-intro' },
            el('p', { className: 'eyebrow' }, 'STUDENT ACCOUNT ACCESS'),
            el('h1', null, 'Request access to your student account.'),
            el('p', { className: 'lead' }, 'If your student record is already in the register, you can request a personal account using a one-time claim code from your administrator.'),
            el('div', { className: 'registration-steps' },
                ...[
                    ['01', 'Ask for your claim code', 'Your administrator issues a private code from your existing student record.'],
                    ['02', 'Enter matching details', 'Use the names, matriculation number, faculty, department and level shown on your record.'],
                    ['03', 'Wait for approval', 'Your request is reviewed before your student account is activated.']
                ].map(([number, title, text]) => el('div', { className: 'registration-step', key: number },
                    el('span', { className: 'registration-step-number' }, number),
                    el('div', null, el('strong', null, title), el('p', null, text))
                ))
            ),
            el('div', { className: 'registration-note' },
                h(Icon, { name: 'shield', size: 18 }),
                el('p', null, 'This form does not create a new student record. It requests account access for a record that already exists.')
            )
        ),
        h(Panel, { className: 'registration-panel' },
            success
                ? el('div', { className: 'registration-success', role: 'status' },
                    el('span', { className: 'success-icon' }, h(Icon, { name: 'check', size: 28 })),
                    el('p', { className: 'eyebrow' }, 'REQUEST RECEIVED'),
                    el('h2', null, 'Your request is in the review queue.'),
                    el('p', null, success),
                    el('p', { className: 'hint' }, 'You do not need to submit another request. Wait for the administrator to review it.'),
                    h(Link, { to: '/login', className: 'button button-primary button-full' }, 'Return to sign in')
                )
                : el('form', { onSubmit: submit, className: 'form-stack' },
                    el('div', { className: 'auth-panel-heading' },
                        el('p', { className: 'eyebrow' }, 'NEW STUDENT ACCOUNT'),
                        el('h2', null, 'Student access request'),
                        el('p', null, 'Enter your information exactly as it appears in the student register.')
                    ),
                    h(Problem, { message: error || catalogue.error }),
                    el('div', { className: 'form-section' },
                        el('h3', null, 'Your student record'),
                        el('p', { className: 'form-section-copy' }, 'These details are checked against your existing record.'),
                        h(Field, {
                            label: 'Matriculation number', name: 'matric_no', required: true,
                            value: form.matric_no, onChange: getInput(setForm, 'matric_no'),
                            autoComplete: 'off', maxLength: 50, placeholder: 'Enter your matriculation number'
                        }),
                        el('div', { className: 'form-grid' },
                            h(Field, { label: 'First name', name: 'first_name', required: true, value: form.first_name, onChange: getInput(setForm, 'first_name'), autoComplete: 'given-name' }),
                            h(Field, { label: 'Middle name', name: 'middle_name', value: form.middle_name, onChange: getInput(setForm, 'middle_name'), autoComplete: 'additional-name', hint: 'Leave blank if your record has no middle name.' }),
                            h(Field, { label: 'Surname', name: 'last_name', required: true, value: form.last_name, onChange: getInput(setForm, 'last_name'), autoComplete: 'family-name' }),
                            h(Field, { label: 'Level', name: 'level', required: true, select: true, choices: ['100', '200', '300', '400', '500', '600'], value: form.level, onChange: getInput(setForm, 'level') }),
                            h(Field, { label: 'Faculty', name: 'faculty', required: true, select: true, choices: catalogue.value?.faculties || [], value: form.faculty, onChange: (event) => setForm((current) => ({ ...current, faculty: event.target.value, department: '' })) }),
                            h(Field, { label: 'Department', name: 'department', required: true, select: true, choices: departmentChoices, value: form.department, onChange: getInput(setForm, 'department'), disabled: !form.faculty || catalogue.loading })
                        )
                    ),
                    el('div', { className: 'form-section' },
                        el('h3', null, 'Verify and secure your account'),
                        el('p', { className: 'form-section-copy' }, 'Your claim code confirms that the administrator has authorised this request.'),
                        h(Field, { label: 'Private one-time claim code', name: 'claim_code', required: true, value: form.claim_code, onChange: getInput(setForm, 'claim_code'), autoComplete: 'off', maxLength: 128, hint: 'Ask your administrator to issue a code if you do not have one.' }),
                        h(Field, { label: 'Create a password', name: 'password', type: 'password', minLength: 12, maxLength: 128, required: true, autoComplete: 'new-password', value: form.password, onChange: getInput(setForm, 'password'), hint: 'Use at least 12 characters.' }),
                        h(Field, { label: 'Confirm password', name: 'confirm', type: 'password', required: true, autoComplete: 'new-password', value: form.confirm, onChange: getInput(setForm, 'confirm') })
                    ),
                    h(Button, { type: 'submit', busy, className: 'button-full', disabled: catalogue.loading || !catalogue.value }, 'Submit account request'),
                    el('p', { className: 'form-note' }, 'Already have an account? ', h(InlineLink, { to: '/login' }, 'Sign in instead'))
                )
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
            description: 'A live overview of the student register, account requests and verification activity.',
            actions: h(Link, { className: 'button button-primary', to: '/verify' }, h(Icon, { name: 'verify', size: 17 }), 'Verify a student')
        }),
        h(Problem, { message: error }),
        loading
            ? h(Spinner, { label: 'Loading your workspace overview…' })
            : value && group(
                el('section', { className: 'stats-grid', 'aria-label': 'StudentVerifi statistics' },
                    h(Stat, { value: total.toLocaleString(), label: 'Students in register', icon: 'students', tone: 'blue', note: 'Total records' }),
                    h(Stat, { value: active.toLocaleString(), label: 'Active students', icon: 'check', tone: 'green', note: activeRate + '% active' }),
                    h(Stat, { value: Number(value.pending || 0).toLocaleString(), label: 'Pending account requests', icon: 'requests', tone: 'amber', note: 'Awaiting review' }),
                    h(Stat, { value: Number(value.verifications || 0).toLocaleString(), label: 'Verification events', icon: 'history', tone: 'violet', note: 'Recorded checks' })
                ),
                el('section', { className: 'dashboard-main-grid' },
                    h(Panel, { className: 'dashboard-panel activity-panel' },
                        el('div', { className: 'panel-heading-row' },
                            el('div', null, el('p', { className: 'eyebrow' }, 'LATEST ACTIVITY'), el('h2', null, 'Recent verification checks'), el('p', { className: 'muted' }, 'The latest recorded verification outcomes.')),
                            h(Link, { to: '/logs', className: 'text-link' }, 'View history', h(Icon, { name: 'arrow', size: 15 }))
                        ),
                        recent.length
                            ? el('div', { className: 'activity-table-wrap' },
                                el('table', { className: 'activity-table' },
                                    el('thead', null, el('tr', null,
                                        el('th', { scope: 'col' }, 'Result'),
                                        el('th', { scope: 'col' }, 'Student / record'),
                                        el('th', { scope: 'col' }, 'Date and time')
                                    )),
                                    el('tbody', null, ...recent.map((item) => el('tr', { key: item.id },
                                        el('td', null, h(Pill, { status: item.result })),
                                        el('td', null, el('strong', null, item.full_name || item.matric_no || 'Unmatched code'), el('span', { className: 'table-secondary' }, item.matric_no || 'No student record')),
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
                            el('h2', null, Number(value.pending || 0).toLocaleString(), ' requests need review'),
                            el('p', null, 'Review student account requests and approve access only after confirming the request is legitimate.'),
                            h(Link, { to: '/registration-requests', className: 'button button-primary button-full' }, 'Open request queue')
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
            description: 'Search the register, review student details and manage each record.',
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
                                        ...['Student', 'Matriculation number', 'Faculty / department', 'Level', 'Status', 'Action'].map((label) =>
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
                        label: 'Email (optional)',
                        name: 'email',
                        type: 'email',
                        value: form.email,
                        onChange: getInput(setForm, 'email')
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
    const [claim, setClaim] = useState('');
    const [qrVersion, setQrVersion] = useState(0);
    const student = value?.student;

    async function mutate(path, body, message) {
        setBusy(true);
        setActionError('');
        try {
            const result = await api('/students/' + id + path, { method: 'POST', body });
            inform(message || result.message);
            if (path === '/rotate-qr') {
                setQrVersion((current) => current + 1);
            }
            reload();
            return result;
        } catch (requestError) {
            setActionError(requestError.message);
            throw requestError;
        } finally {
            setBusy(false);
        }
    }

    async function issueClaimCode() {
        try {
            const result = await mutate('/claim-code', {}, 'A private claim code has been issued.');
            setClaim(result.code);
        } catch (requestError) {
            // The page displays the action error returned by mutate().
        }
    }

    async function copyClaimCode() {
        try {
            await navigator.clipboard.writeText(claim);
            inform('Claim code copied.');
        } catch (requestError) {
            inform('Copy was unavailable. Select and copy the code manually.', 'error');
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
                        student.photo_url
                            ? el('img', {
                                src: student.photo_url,
                                alt: 'Student record photograph',
                                className: 'profile-image',
                                referrerPolicy: 'no-referrer'
                            })
                            : el('div', {
                                className: 'profile-placeholder',
                                'aria-hidden': 'true'
                            }, (student.name || '?').slice(0, 1)),
                        el('div', null,
                            el('h2', null, student.name),
                            h(Pill, { status: student.status })
                        )
                    ),
                    el('dl', { className: 'detail-list' },
                        h(DetailRow, { label: 'Matriculation number', value: student.matric_no }),
                        h(DetailRow, { label: 'Faculty', value: student.faculty }),
                        h(DetailRow, { label: 'Department', value: student.department }),
                        h(DetailRow, { label: 'Level', value: student.level }),
                        h(DetailRow, { label: 'Email', value: student.email }),
                        h(DetailRow, { label: 'Created', value: compactDate(student.created_at) })
                    ),
                    h(ConfirmAction, {
                        title: (student.status === 'Active' ? 'Deactivate' : 'Activate') + ' student?',
                        text: 'This changes whether the student QR credential verifies as active.',
                        busy,
                        dangerous: student.status === 'Active',
                        action: () => mutate('/status', {
                            status: student.status === 'Active' ? 'Inactive' : 'Active'
                        })
                    }, student.status === 'Active' ? 'Deactivate student' : 'Activate student')
                ),
                h(Panel, null,
                    el('h2', null, 'QR credential'),
                    el('p', { className: 'muted' }, 'This unique QR credential is linked to the student record. Compare the person with authorised identity evidence.'),
                    el('img', {
                        className: 'qr-image',
                        alt: 'Student QR code',
                        src: '/api/students/' + id + '/qr.png?v=' + qrVersion
                    }),
                    el('div', { className: 'stacked-actions' },
                        el('a', {
                            className: 'button button-outline',
                            href: '/api/students/' + id + '/qr.png',
                            download: true
                        }, 'Download QR'),
                        h(ConfirmAction, {
                            title: 'Rotate this QR credential?',
                            text: 'The previous QR code will immediately stop working.',
                            dangerous: true,
                            busy,
                            action: () => mutate('/rotate-qr', {}, 'Student QR credential refreshed.')
                        }, 'Rotate QR credential'),
                        h(Button, {
                            variant: 'outline',
                            busy,
                            onClick: issueClaimCode
                        }, 'Issue student claim code')
                    ),
                    claim && el('div', { className: 'claim-box', role: 'status' },
                        el('strong', null, 'One-time claim code — copy it now'),
                        el('code', null, claim),
                        h(Button, { variant: 'outline', onClick: copyClaimCode }, 'Copy private code'),
                        el('p', { className: 'hint' }, 'Share this code privately with the correct student. It will not be displayed again.')
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
                    hint: 'Only import authorised institutional records. Validate your file before uploading.'
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
    const [token, setToken] = useState('');
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    async function check(value) {
        setError('');
        setResult(null);
        if (!value.trim()) {
            setError('Enter a verification code.');
            return;
        }
        setBusy(true);
        try {
            setResult(await api('/verify', {
                method: 'POST',
                body: { token: value.trim() }
            }));
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBusy(false);
        }
    }

    async function onScan(code) {
        setToken(code);
        await check(code);
    }

    return group(
        h(TitleBlock, {
            eyebrow: 'IDENTITY VERIFICATION',
            title: 'Verify a student',
            description: 'Scan a QR credential or enter its code to check the current student record status.'
        }),
        el('div', { className: 'two-col' },
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
                h(Problem, { message: error }),
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
                        result.student.photo_url && el('img', {
                            src: result.student.photo_url,
                            alt: 'Student record photograph',
                            className: 'profile-image',
                            referrerPolicy: 'no-referrer'
                        }),
                        el('div', null,
                            el('strong', null, result.student.name),
                            el('p', null, result.student.matric_no),
                            el('p', null, `${result.student.department} · ${result.student.level} level`),
                            h(Link, {
                                to: '/students/' + result.student.id,
                                className: 'text-link'
                            }, 'View student record')
                        )
                    ),
                    el('p', { className: 'notice' }, 'Check the person’s identity independently. A copied QR code is not proof that its holder is the student.')
                )
            )
        )
    );
}

export function Requests() {
    const { inform } = useAuth();
    const { value, loading, error, reload } = useResource('/registration-requests');
    const [busy, setBusy] = useState(0);
    const [actionError, setActionError] = useState('');

    async function decide(id, choice) {
        setBusy(id);
        setActionError('');
        try {
            const result = await api('/registration-requests/' + id + '/' + choice, {
                method: 'POST',
                body: {}
            });
            inform(result.message);
            reload();
        } catch (requestError) {
            setActionError(requestError.message);
        } finally {
            setBusy(0);
        }
    }

    return group(
        h(TitleBlock, {
            eyebrow: 'ACCOUNT ACCESS',
            title: 'Registration requests',
            description: 'Review student requests before granting access to an account.'
        }),
        h(Problem, { message: error || actionError }),
        loading
            ? h(Spinner)
            : value?.items?.length
                ? el('div', { className: 'cards-list' },
                    ...value.items.map((item) => h(Panel, { key: item.id },
                        el('div', { className: 'request-row' },
                            el('div', null,
                                el('h2', null, item.name),
                                el('p', null, item.matric_no + ' · ' + item.department),
                                el('p', { className: 'hint' }, 'Requested ' + compactDate(item.requested_at))
                            ),
                            el('div', { className: 'actions' },
                                h(Button, {
                                    variant: 'outline',
                                    busy: busy === item.id,
                                    onClick: () => decide(item.id, 'reject')
                                }, 'Reject'),
                                h(ConfirmAction, {
                                    title: 'Approve student account?',
                                    text: `You are about to grant account access for ${item.matric_no}. Confirm that this request is authorised.`,
                                    busy: busy === item.id,
                                    action: () => decide(item.id, 'approve')
                                }, 'Approve')
                            )
                        )
                    ))
                )
                : h(Empty, {
                    title: 'No pending requests',
                    text: 'All current student account requests have been reviewed.'
                })
    );
}

export function EventLogs({ audit = false }) {
    const { value, loading, error } = useResource(audit ? '/admin-audit' : '/logs');
    const headings = audit
        ? ['Action', 'Details', 'Administrator', 'Time']
        : ['Outcome', 'Student', 'Verifier', 'Time'];

    return group(
        h(TitleBlock, {
            eyebrow: audit ? 'ACCOUNTABILITY' : 'VERIFICATION',
            title: audit ? 'Administrative activity' : 'Verification history',
            description: audit
                ? 'A record of important administrative changes.'
                : 'Recent QR verification outcomes. Reusable QR secrets are not displayed.'
        }),
        h(Problem, { message: error }),
        loading
            ? h(Spinner)
            : value?.items?.length
                ? h(Panel, null,
                    el('div', { className: 'table-scroll' },
                        el('table', null,
                            el('thead', null,
                                el('tr', null,
                                    ...headings.map((heading) => el('th', {
                                        key: heading,
                                        scope: 'col'
                                    }, heading))
                                )
                            ),
                            el('tbody', null,
                                ...value.items.map((item) => el('tr', { key: item.id },
                                    audit
                                        ? group(
                                            el('td', null, String(item.event || '').replaceAll('_', ' ')),
                                            el('td', null, item.details),
                                            el('td', null, item.actor || 'System'),
                                            el('td', null, compactDate(item.created_at))
                                        )
                                        : group(
                                            el('td', null, h(Pill, { status: item.result })),
                                            el('td', null, item.matric_no || 'Unknown / invalid code'),
                                            el('td', null, item.verified_by_name || '—'),
                                            el('td', null, compactDate(item.verified_at))
                                        )
                                ))
                            )
                        )
                    )
                )
                : h(Empty, {
                    title: 'No events recorded',
                    text: 'New events will appear here after authorised activity.'
                })
    );
}

export function StudentAccount() {
    const { value, loading, error } = useResource('/student/me');
    const student = value?.student;

    return group(
        h(TitleBlock, {
            eyebrow: 'STUDENT SPACE',
            title: 'My student card',
            description: 'View your student details and access your QR credential when needed.',
            actions: h(Link, { className: 'button button-outline', to: '/account/password' }, 'Change password')
        }),
        h(Problem, { message: error }),
        loading
            ? h(Spinner)
            : student && el('div', { className: 'two-col' },
                h(Panel, null,
                    el('h2', null, student.name),
                    h(Pill, { status: student.status }),
                    el('dl', { className: 'detail-list' },
                        h(DetailRow, { label: 'Matriculation number', value: student.matric_no }),
                        h(DetailRow, { label: 'Faculty', value: student.faculty }),
                        h(DetailRow, { label: 'Department', value: student.department }),
                        h(DetailRow, { label: 'Level', value: student.level })
                    )
                ),
                h(Panel, null,
                    el('h2', null, 'My QR credential'),
                    student.status === 'Active'
                        ? group(
                            el('img', {
                                src: '/api/student/my-qr.png',
                                alt: 'Your unique student QR credential',
                                className: 'qr-image'
                            }),
                            el('a', {
                                href: '/api/student/my-qr.png',
                                className: 'button button-primary',
                                download: true
                            }, 'Download my QR code')
                        )
                        : el('p', { className: 'notice' }, 'Your QR credential is unavailable while your record is inactive.'),
                    el('p', { className: 'hint' }, 'Protect this QR code. A verifier should still check your identity independently.')
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

export function Missing() {
    return el('div', { className: 'center-block' },
        el('span', { className: 'access-icon' }, h(Icon, { name: 'file', size: 26 })),
        el('h1', null, 'Page not found'),
        el('p', null, 'The page you requested does not exist or may have moved.'),
        h(Link, { to: '/', className: 'button button-primary' }, 'Return to homepage')
    );
}
