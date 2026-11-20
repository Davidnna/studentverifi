import React, { createContext, useContext, useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api, setCsrf } from './api.js';

export const h = React.createElement;
const AuthContext = createContext(null);

export function useAuth() { return useContext(AuthContext); }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const ctl = new AbortController();
    api('/session', { signal: ctl.signal }).then(data => {
      setUser(data.user); setCsrf(data.csrf_token); setError('');
    }).catch(e => { if (e.name !== 'AbortError') setError(e.message); })
      .finally(() => { if (!ctl.signal.aborted) setLoading(false); });
    return () => ctl.abort();
  }, []);
  const value = {
    user, loading, error, setUser,
    inform: (message, type='success') => setToast({ message, type }),
    dismiss: () => setToast(null),
    login: async (username, password) => {
      const data = await api('/login', { method:'POST', body:{username,password} });
      setCsrf(data.csrf_token); setUser(data.user); return data.user;
    },
    logout: async () => { await api('/logout', {method:'POST'}); setCsrf(''); setUser(null); }
  };
  return h(AuthContext.Provider, {value}, children,
    toast && h('div', {className:'toast', role: toast.type === 'error' ? 'alert' : 'status'},
      h('p', null, toast.message),
      h('button', {type:'button', className:'icon-button', onClick:()=>setToast(null), 'aria-label':'Dismiss notification'}, '×'))
  );
}

export function Button({ children, className='', variant='primary', busy=false, type='button', ...props }) {
  return h('button', {type, className:'button button-'+variant+' '+className, disabled:busy || props.disabled, ...props},
    busy ? h('span', {className:'spinner', 'aria-hidden':'true'}) : null, children);
}
export function Panel({children, className='', ...props}) {
  return h('section',{className:'panel '+className,...props},children);
}
export function TitleBlock({eyebrow, title, description, actions}) {
  return h('div',{className:'page-title'},
    h('div', null, eyebrow && h('p',{className:'eyebrow'},eyebrow),h('h1',null,title),description&&h('p',{className:'lead'},description)),
    actions && h('div',{className:'actions'},actions));
}
export function Pill({ status }) {
  const normalized=String(status||'Unknown').toLowerCase();
  const theme = ['valid','active','approved','success'].includes(normalized) ? 'good' :
    ['invalid','rejected','revoked'].includes(normalized) ? 'bad' : 'neutral';
  return h('span',{className:'pill pill-'+theme},String(status||'Unknown'));
}
export function Field({label, name, hint, error, select, choices, textarea, ...props}) {
  const id=props.id||name;
  const base={id,name,'aria-describedby':(hint||error)?id+'-help':undefined,'aria-invalid':!!error,...props};
  const control= select ? h('select',base,h('option',{value:''},'Choose an option'),...(choices||[]).map(x=>h('option',{key: typeof x === 'string' ? x : x.value,value:typeof x === 'string'?x:x.value},typeof x === 'string'?x:x.label)))
    : textarea ? h('textarea',base) : h('input',base);
  return h('div',{className:'field'},h('label',{htmlFor:id},label),control,
    (hint||error) && h('small',{id:id+'-help',className:error?'field-error':'hint'},error||hint));
}
export function Problem({message}) { return message ? h('div',{className:'alert alert-error',role:'alert'},message) : null; }
export function Empty({title='Nothing here yet',text='Try a different search or come back later.'}) {
  return h('div',{className:'empty'},h('h3',null,title),h('p',null,text));
}
export function Spinner({label='Loading…'}) { return h('div',{className:'loading',role:'status'},h('span',{className:'spinner','aria-hidden':'true'}),label); }
export function ConfirmAction({title, text, action, dangerous=false, children, busy=false}) {
  const [open,setOpen]=useState(false);
  const triggerRef=React.useRef(null);
  const cancelRef=React.useRef(null);
  const dialogRef=React.useRef(null);
  function close(){setOpen(false);triggerRef.current?.focus();}
  useEffect(()=>{
    if(!open)return;
    cancelRef.current?.focus();
    const onKey=(event)=>{
      if(event.key==='Escape'){event.preventDefault();close();return;}
      if(event.key==='Tab' && dialogRef.current){
        const controls=[...dialogRef.current.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled)')];
        if(!controls.length)return;
        if(event.shiftKey&&document.activeElement===controls[0]){event.preventDefault();controls[controls.length-1].focus();}
        else if(!event.shiftKey&&document.activeElement===controls[controls.length-1]){event.preventDefault();controls[0].focus();}
      }
    };
    document.addEventListener('keydown',onKey);
    return()=>document.removeEventListener('keydown',onKey);
  },[open]);
  return h(React.Fragment,null,
    h('button',{type:'button',ref:triggerRef,className:'button button-'+(dangerous?'danger':'outline'),onClick:()=>setOpen(true),disabled:busy},children),
    open && h('div',{className:'modal-backdrop',role:'presentation'},
      h('div',{ref:dialogRef,role:'dialog','aria-modal':'true','aria-labelledby':'confirm-action-title',
        'aria-describedby':'confirm-action-text',className:'dialog'},
        h('h2',{id:'confirm-action-title'},title),h('p',{id:'confirm-action-text'},text),
        h('div',{className:'actions'},
          h('button',{type:'button',ref:cancelRef,className:'button button-outline',onClick:close},'Cancel'),
          h(Button,{variant:dangerous?'danger':'primary',busy,onClick:async()=>{
            try {await action();close();}catch(e) { /* caller renders action errors */ }
          }},'Confirm')))));
}

const publicLinks = [['/','Home'],['/how-it-works','How it works'],['/faq','FAQ'],['/about','About']];
const adminLinks = [['/dashboard','Overview'],['/students','Students'],['/verify','Verify identity'],['/registration-requests','Registration requests'],['/logs','Verification history'],['/admin-audit','Admin audit'],['/account/password','Password']];
function NavGroup({links, close}) {
  return h(React.Fragment,null,...links.map(([to,label])=>h(NavLink,
    {key:to,to,onClick:close,end:to==='/',className:({isActive})=>'nav-link '+(isActive?'selected':'')},label)));
}
export function AppShell() {
  const {user, loading, error, logout, inform}=useAuth();
  const [menuOpen,setMenuOpen]=useState(false);
  const navigate=useNavigate();
  const location=useLocation();
  useEffect(()=>{setMenuOpen(false);document.getElementById('main-content')?.focus();window.scrollTo(0,0);},[location.pathname]);
  useEffect(()=>{ document.title='StudentVerifi · '+(document.querySelector('h1')?.textContent||'Student identity verification');},[location.pathname]);
  const links=user?.role==='admin'?adminLinks:user?.role==='student'?[['/student/account','My student card'],['/account/password','Change password']]:publicLinks;
  const close=()=>setMenuOpen(false);
  async function signout(){try{await logout();navigate('/login');inform('Signed out successfully.');}catch(e){inform(e.message,'error');}}
  return h('div',{className:'app-shell'},
    h('a',{href:'#main-content',className:'skip-link'},'Skip to main content'),
    h('header',{className:'site-header'},
      h(Link,{to:'/',className:'brand',onClick:close,'aria-label':'StudentVerifi home'},
        h('img',{src:'/logo.svg',alt:'StudentVerifi',width:176,height:40})),
      h('button',{type:'button',className:'menu-toggle',onClick:()=>setMenuOpen(v=>!v),
        'aria-label':menuOpen?'Close menu':'Open menu','aria-expanded':menuOpen,'aria-controls':'primary-nav'},menuOpen?'Close':'Menu'),
      h('nav',{id:'primary-nav',className:'site-nav '+(menuOpen?'open':''),'aria-label':'Primary navigation'},
        h(NavGroup,{links,close}),
        !loading && (user ? h(Button,{variant:'ghost',onClick:signout},'Sign out') : h(Link,{to:'/login',className:'button button-primary',onClick:close},'Sign in')))),
    h('main',{id:'main-content',className:'container',tabIndex:-1},
      error && h(Problem,{message:error}),h(Outlet)),
    h('footer',{className:'site-footer'},h('span',null,'StudentVerifi · Academic prototype'),
      h('div',{className:'footer-links'},h(Link,{to:'/privacy'},'Privacy'),h(Link,{to:'/contact'},'Contact'))));
}

export function Protected({role}) {
  const {user,loading}=useAuth();
  if(loading) return h(Spinner,{label:'Checking your session…'});
  if(!user) return h('div',{className:'center-block'},h('h1',null,'Sign in required'),h('p',null,'Sign in to access this page.'),h(Link,{to:'/login',className:'button button-primary'},'Sign in'));
  if(role && user.role !== role) return h('div',{className:'center-block'},h('h1',null,'Access restricted'),h('p',null,'Your account cannot access this page.'),h(Link,{to:'/',className:'button button-outline'},'Go home'));
  return h(Outlet);
}
