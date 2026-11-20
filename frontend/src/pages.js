import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, compactDate } from './api.js';
import { h, useAuth, Button, Panel, TitleBlock, Pill, Field, Problem, Empty, Spinner, ConfirmAction } from './components.js';

const el=(tag,props,...children)=>h(tag,props,...children);
const group=(...children)=>h(React.Fragment,null,...children);

function useResource(path) {
  const [value,setValue]=useState(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [nonce,setNonce]=useState(0);
  useEffect(()=>{
    const ctl=new AbortController();
    setLoading(true);setError('');
    api(path,{signal:ctl.signal}).then(setValue).catch(e=>{if(e.name!=='AbortError')setError(e.message);})
      .finally(()=>{if(!ctl.signal.aborted)setLoading(false);});
    return ()=>ctl.abort();
  },[path,nonce]);
  return {value,loading,error,reload:()=>setNonce(x=>x+1)};
}
function Stat({value,label}) {return el('div',{className:'stat'},el('span',{className:'stat-value'},value??'—'),el('span',{className:'stat-label'},label));}
function DetailRow({label,value}) {return group(el('dt',null,label),el('dd',null,value||'—'));}
function FormActions({children}) {return el('div',{className:'form-actions'},children);}
function getInput(setter,field) {return e=>setter(s=>({...s,[field]:e.target.value}));}
function InlineLink({to,children}) {return h(Link,{to,className:'text-link'},children);}

export function Home() {
  return group(
    el('section',{className:'hero'},
      el('div',null,el('p',{className:'eyebrow'},'Student identity, simplified'),
        el('h1',null,'Verify students with clarity and confidence.'),
        el('p',{className:'hero-subtitle'},'One straightforward place for QR-based identity checks, student records and administrative workflows.'),
        el('div',{className:'actions'},h(Link,{className:'button button-primary',to:'/login'},'Sign in to StudentVerifi'),
          h(Link,{className:'button button-outline',to:'/how-it-works'},'How it works'))),
      el('div',{className:'hero-visual','aria-hidden':'true'},
        el('div',{className:'mock-card'},el('div',{className:'mock-icon'},'✓'),
          el('p',{className:'mock-caption'},'Identity verification'),
          el('h2',null,'Clear result. Fast decision.'),
          el('div',{className:'mock-line'}),el('div',{className:'mock-line short'})))),
    el('section',{className:'section-spacing','aria-label':'Features'},
      el('div',{className:'feature-grid'},
        el('article',{className:'feature'},el('span',{className:'feature-icon','aria-hidden':'true'},'01'),el('h2',null,'Scan and verify'),el('p',null,'Use the rear camera on your phone, choose another camera or enter a QR token manually.')),
        el('article',{className:'feature'},el('span',{className:'feature-icon','aria-hidden':'true'},'02'),el('h2',null,'Manage records'),el('p',null,'Find students, check registration status and manage QR credentials from one dashboard.')),
        el('article',{className:'feature'},el('span',{className:'feature-icon','aria-hidden':'true'},'03'),el('h2',null,'Review outcomes'),el('p',null,'See verification results and administrative activity with access controls.')))),
    el('p',{className:'notice'},'StudentVerifi is an academic prototype. A QR match establishes the status of a stored record; identity also requires authorised photograph or document comparison.'));
}
const infoContent={
  '/how-it-works':{title:'How StudentVerifi works',intro:'A straightforward journey from the student register to an identity-check result.',steps:[['1. Create a record','An administrator adds an authorised student record or imports records from a validated CSV file.'],['2. Issue a QR credential','A unique, opaque QR credential is made available to the administrator and the authorised student.'],['3. Verify securely','An authorised verifier scans the code or enters it manually; StudentVerifi checks the current student status.'],['4. Confirm identity','The verifier compares the person with authorised identification or a reliable student photograph.']]},
  '/about':{title:'About StudentVerifi',intro:'StudentVerifi is a university-oriented academic prototype for QR-code-assisted student identity verification.',steps:[['Purpose','Provide an accessible, mobile-friendly system for student management and verification.'],['Privacy','Sensitive information should be accessible only to authorised users, and real records require institutional approval.']]},
  '/faq':{title:'Frequently asked questions',intro:'Answers to common student and verifier questions.',steps:[['Why does the camera ask permission?','Your browser must receive permission to access your phone camera. You can also enter a QR token manually.'],['Why is my QR code marked inactive?','The student record is not currently active. Contact the authorised institution administrator.'],['Does a valid QR code prove the person’s identity?','No. A valid code confirms a matching active record. A verifier must also check the person’s identification.'],['How do students create accounts?','An administrator issues a private claim code; students request an account and an administrator approves it.']]},
  '/privacy':{title:'Privacy and responsible use',intro:'This prototype processes identity information only for approved academic and testing purposes.',steps:[['Authorised access','Student data and QR credentials should only be used by people with an approved role.'],['Data handling','Do not upload genuine university records without authorisation, a privacy notice and a retention policy.'],['Test data','Records marked DEMO are fictional and cannot be treated as authentic university identities.']]},
  '/contact':{title:'Contact and support',intro:'For account access, student information corrections or verification concerns, contact the administrator responsible for your StudentVerifi installation.',steps:[['Account requests','Students must obtain a private claim code from an administrator before registering.'],['Technical help','For a camera issue, check browser camera permission and try the manual entry option.']]}
};
export function InfoPage({page}) {
  const data=infoContent[page]||infoContent['/about'];
  return group(h(TitleBlock,{eyebrow:'Information',title:data.title,description:data.intro}),
    el('div',{className:'info-grid'},...data.steps.map(([name,body])=>el('article',{key:name,className:'panel'},el('h2',null,name),el('p',null,body)))));
}

export function Login() {
  const {user, login, inform}=useAuth();
  const navigate=useNavigate();
  const [form,setForm]=useState({username:'',password:''});
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{if(user)navigate(user.role==='admin'?'/dashboard':'/student/account',{replace:true});},[user,navigate]);
  async function submit(e){e.preventDefault();setError('');setBusy(true);
    try{const result=await login(form.username,form.password);inform('Signed in.');navigate(result.role==='admin'?'/dashboard':'/student/account',{replace:true});}
    catch(ex){setError(ex.message);}finally{setBusy(false);}}
  return el('div',{className:'auth-layout'},
    el('div',null,el('p',{className:'eyebrow'},'Welcome back'),el('h1',null,'Sign in to StudentVerifi'),el('p',{className:'lead'},'Access your student card or the authorised verification dashboard.')),
    h(Panel,{className:'auth-panel'},el('form',{onSubmit:submit,className:'form-stack'},
      h(Problem,{message:error}),h(Field,{label:'Username or matriculation number',name:'username',autoComplete:'username',value:form.username,onChange:getInput(setForm,'username'),required:true}),
      h(Field,{label:'Password',name:'password',type:'password',autoComplete:'current-password',value:form.password,onChange:getInput(setForm,'password'),required:true}),
      h(Button,{type:'submit',busy,className:'button-full'},'Sign in'),
      el('p',{className:'form-note'},'Are you a student without an account? ',h(InlineLink,{to:'/register'},'Request access')))));
}
export function Register() {
  const [form,setForm]=useState({matric_no:'',claim_code:'',password:'',confirm:''});
  const [error,setError]=useState(''),[success,setSuccess]=useState(''),[busy,setBusy]=useState(false);
  async function submit(e){e.preventDefault();setError('');setSuccess('');
    if(form.password!==form.confirm){setError('The passwords do not match.');return;}
    setBusy(true);try{const out=await api('/register',{method:'POST',body:form});setSuccess(out.message);setForm({matric_no:'',claim_code:'',password:'',confirm:''});}catch(ex){setError(ex.message);}finally{setBusy(false);}}
  return el('div',{className:'auth-layout'},
    el('div',null,el('p',{className:'eyebrow'},'Student access'),el('h1',null,'Request a student account'),el('p',{className:'lead'},'You need a private claim code issued by an administrator. Your request will be reviewed before you can sign in.')),
    h(Panel,{className:'auth-panel'},el('form',{onSubmit:submit,className:'form-stack'},
      h(Problem,{message:error}),success&&el('p',{role:'status',className:'alert alert-success'},success),
      h(Field,{label:'Matriculation number',name:'matric_no',required:true,value:form.matric_no,onChange:getInput(setForm,'matric_no'),autoComplete:'off'}),
      h(Field,{label:'Private claim code',name:'claim_code',required:true,value:form.claim_code,onChange:getInput(setForm,'claim_code'),autoComplete:'off',hint:'Ask your authorised administrator for your one-time code.'}),
      h(Field,{label:'Choose a password',name:'password',type:'password',minLength:12,maxLength:128,required:true,autoComplete:'new-password',value:form.password,onChange:getInput(setForm,'password'),hint:'At least 12 characters.'}),
      h(Field,{label:'Confirm password',name:'confirm',type:'password',required:true,value:form.confirm,onChange:getInput(setForm,'confirm'),autoComplete:'new-password'}),
      h(Button,{type:'submit',busy,className:'button-full'},'Submit account request'),
      el('p',{className:'form-note'},'Already registered? ',h(InlineLink,{to:'/login'},'Sign in')))));
}

export function Dashboard() {
  const {value,loading,error}=useResource('/dashboard');
  return group(h(TitleBlock,{eyebrow:'Administration',title:'Overview',description:'The most important records and activity at a glance.',
      actions:h(Link,{className:'button button-primary',to:'/verify'},'Verify a student')}),
    h(Problem,{message:error}), loading ? h(Spinner) : value && group(
      el('div',{className:'stats-grid'},h(Stat,{value:value.students,label:'Students registered'}),h(Stat,{value:value.active,label:'Active students'}),h(Stat,{value:value.pending,label:'Requests awaiting review'}),h(Stat,{value:value.verifications,label:'Verification events'})),
      el('div',{className:'two-col section-spacing'},
        h(Panel,null,el('h2',null,'Student management'),el('p',null,'Search, add and manage student records from one location.'),h(Link,{to:'/students',className:'button button-outline'},'Open student directory')),
        h(Panel,null,el('h2',null,'Verify student ID'),el('p',null,'Scan a QR code using a phone or verify a token manually.'),h(Link,{to:'/verify',className:'button button-primary'},'Open verifier')))));
}
export function Students() {
  const [draft,setDraft]=useState(''),[query,setQuery]=useState(''),[page,setPage]=useState(1),[status,setStatus]=useState('');
  const suffix=`/students?page=${page}&limit=20&q=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`;
  const {value,loading,error}=useResource(suffix);
  return group(h(TitleBlock,{eyebrow:'Student records',title:'Students',description:'Search the register and manage each student’s details.',
    actions:group(h(Link,{to:'/students/demo-cleanup',className:'button button-outline'},'Manage demo data'),h(Link,{to:'/students/import',className:'button button-outline'},'Import CSV'),h(Link,{to:'/students/new',className:'button button-primary'},'Add student'))}),
    h(Panel,null,el('form',{className:'search-bar',onSubmit:e=>{e.preventDefault();setPage(1);setQuery(draft);},role:'search'},
      h(Field,{label:'Find a student',name:'student-search',value:draft,onChange:e=>setDraft(e.target.value),placeholder:'Name, matriculation number or department'}),
      h(Field,{label:'Status',name:'status-filter',select:true,value:status,onChange:e=>{setStatus(e.target.value);setPage(1);},choices:['Active','Inactive']}),
      h(Button,{type:'submit'},'Search')),
      h(Problem,{message:error}),loading ? h(Spinner) : value && group(
        el('p',{className:'results-count',role:'status'},`${value.total} student${value.total===1?'':'s'} found`),
        value.items.length ? el('div',{className:'table-scroll'},el('table',null,
          el('thead',null,el('tr',null,el('th',{scope:'col'},'Student'),el('th',{scope:'col'},'Matriculation no.'),el('th',{scope:'col'},'Faculty / department'),el('th',{scope:'col'},'Level'),el('th',{scope:'col'},'Status'),el('th',{scope:'col'},'Action'))),
          el('tbody',null,...value.items.map(s=>el('tr',{key:s.id},
            el('td',null,el('strong',null,s.name)),el('td',null,s.matric_no),el('td',null,s.faculty?s.faculty+' · '+s.department:s.department),
            el('td',null,s.level),el('td',null,h(Pill,{status:s.status})),el('td',null,h(Link,{className:'text-link',to:'/students/'+s.id},'View')))))))
          : h(Empty,{title:'No matching students',text:'Try another search or add a new student.'}),
        el('nav',{className:'pagination','aria-label':'Student pages'},
          h(Button,{variant:'outline',disabled:page===1,onClick:()=>setPage(x=>Math.max(1,x-1))},'Previous'),
          el('span',null,`Page ${page} of ${Math.max(1,Math.ceil(value.total/20))}`),
          h(Button,{variant:'outline',disabled:page*20>=value.total,onClick:()=>setPage(x=>x+1)},'Next')))));
}
export function StudentForm() {
  const {inform}=useAuth(),navigate=useNavigate();
  const [d,setD]=useState({matric_no:'',first_name:'',middle_name:'',last_name:'',faculty:'',department:'',level:'',email:'',status:'Active'});
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const catalogue=useResource('/catalogue');
  async function submit(e){e.preventDefault();setError('');setBusy(true);
    try{const data=await api('/students',{method:'POST',body:d});inform('Student record created.');navigate('/students/'+data.id);}
    catch(ex){setError(ex.message);}finally{setBusy(false);}}
  return group(h(TitleBlock,{eyebrow:'Students',title:'Add student',description:'Complete the student information. Only authorised student records should be added.'}),
    h(Panel,{className:'form-panel'},el('form',{className:'form-stack',onSubmit:submit},
      h(Problem,{message:error}),
      el('div',{className:'form-grid'},
        h(Field,{label:'Matriculation number',name:'matric_no',required:true,value:d.matric_no,onChange:getInput(setD,'matric_no')}),
        h(Field,{label:'First name',name:'first_name',required:true,value:d.first_name,onChange:getInput(setD,'first_name')}),
        h(Field,{label:'Middle name (optional)',name:'middle_name',value:d.middle_name,onChange:getInput(setD,'middle_name')}),
        h(Field,{label:'Surname',name:'last_name',required:true,value:d.last_name,onChange:getInput(setD,'last_name')}),
        h(Field,{label:'Faculty',name:'faculty',required:true,value:d.faculty,onChange:getInput(setD,'faculty'),list:'faculties-list'}),
        h(Field,{label:'Department',name:'department',required:true,value:d.department,onChange:getInput(setD,'department'),list:'departments-list'}),
        h(Field,{label:'Level',name:'level',select:true,choices:['100','200','300','400','500','600'],required:true,value:d.level,onChange:getInput(setD,'level')}),
        h(Field,{label:'Email (optional)',name:'email',type:'email',value:d.email,onChange:getInput(setD,'email')})),
      el('datalist',{id:'faculties-list'},...(catalogue.value?.faculties||[]).map(x=>el('option',{key:x,value:x}))),
      el('datalist',{id:'departments-list'},...(catalogue.value?.departments||[]).map(x=>el('option',{key:x,value:x}))),
      h(Problem,{message:catalogue.error}),
      h(FormActions,null,h(Link,{className:'button button-outline',to:'/students'},'Cancel'),h(Button,{type:'submit',busy},'Save student')))));
}

export function StudentDetail() {
  const {id}=useParams(),{inform}=useAuth();
  const {value,loading,error,reload}=useResource('/students/'+id);
  const [busy,setBusy]=useState(false),[actionError,setActionError]=useState(''),[claim,setClaim]=useState(''),[qrVersion,setQrVersion]=useState(0);
  async function mutate(path,body,message){setBusy(true);setActionError('');try{const out=await api('/students/'+id+path,{method:'POST',body});inform(message||out.message);if(path==='/rotate-qr')setQrVersion(x=>x+1);reload();return out;}
      catch(e){setActionError(e.message);throw e;}finally{setBusy(false);}}
  const s=value?.student;
  return group(h(TitleBlock,{eyebrow:'Student record',title:s?.name||'Student details',description:s?.matric_no||'View and manage the selected student record.',
    actions:h(Link,{className:'button button-outline',to:'/students'},'Back to students')}),
    h(Problem,{message:error||actionError}),loading?h(Spinner):s && el('div',{className:'two-col'},
      h(Panel,null,el('div',{className:'student-heading'},s.photo_url
        ? el('img',{src:s.photo_url,alt:'Student record photograph',className:'profile-image',referrerPolicy:'no-referrer'})
        : el('div',{className:'profile-placeholder','aria-hidden':'true'},(s.name||'?').slice(0,1)),
        el('div',null,el('h2',null,s.name),h(Pill,{status:s.status}))),
        el('dl',{className:'detail-list'},h(DetailRow,{label:'Matriculation number',value:s.matric_no}),
          h(DetailRow,{label:'Faculty',value:s.faculty}),h(DetailRow,{label:'Department',value:s.department}),
          h(DetailRow,{label:'Level',value:s.level}),h(DetailRow,{label:'Email',value:s.email}),
          h(DetailRow,{label:'Created',value:compactDate(s.created_at)})),
        h(ConfirmAction,{title:(s.status==='Active'?'Deactivate':'Activate')+' student?',
          text:'This changes whether their QR credential verifies as active.',busy,
          dangerous:s.status==='Active',action:()=>mutate('/status',{status:s.status==='Active'?'Inactive':'Active'})},
          s.status==='Active'?'Deactivate student':'Activate student')),
      h(Panel,null,el('h2',null,'QR credential'),el('p',{className:'muted'},'Unique QR for this student. Compare the person with authorised identity evidence.'),
        el('img',{className:'qr-image',alt:'Student QR code',src:'/api/students/'+id+'/qr.png?v='+qrVersion}),
        el('div',{className:'stacked-actions'},el('a',{className:'button button-outline',href:'/api/students/'+id+'/qr.png',download:true},'Download QR'),
        h(ConfirmAction,{title:'Rotate this QR credential?',text:'The previous QR code will immediately stop working.',dangerous:true,busy,
          action:()=>mutate('/rotate-qr',{},'QR credential rotated.')},'Rotate QR credential'),
        h(Button,{variant:'outline',busy,onClick:async()=>{try{const result=await mutate('/claim-code',{});setClaim(result.code);}catch(e){}}},'Issue student claim code')),
        claim && el('div',{className:'claim-box',role:'status'},
          el('strong',null,'One-time claim code (copy now)'),el('code',null,claim),
          h(Button,{variant:'outline',onClick:()=>navigator.clipboard?.writeText(claim).then(()=>inform('Claim code copied.')).catch(()=>inform('Copy manually if your browser blocks clipboard.','error'))},'Copy private code'),
          el('p',{className:'hint'},'Give this privately to the correct student. It will not appear again.')))));
}

export function StudentImport() {
  const {inform}=useAuth(),navigate=useNavigate();
  const [file,setFile]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[details,setDetails]=useState([]);
  async function submit(e){e.preventDefault();if(!file)return;setBusy(true);setError('');setDetails([]);
    const form=new FormData();form.set('file',file);
    try{const r=await api('/students/import',{method:'POST',body:form});inform(r.message);navigate('/students');}
    catch(ex){setError(ex.message);setDetails(ex.details||[]);}finally{setBusy(false);}}
  return group(h(TitleBlock,{eyebrow:'Student records',title:'Import students',description:'Upload a UTF-8 CSV file with no more than 5,000 records (maximum 2 MB). The import is all-or-nothing.'}),
    h(Panel,{className:'form-panel'},
      el('p',null,'Download the template to see the required column headings and example format.'),
      el('a',{href:'/api/students/import-template',className:'button button-outline'},'Download CSV template'),
      el('form',{className:'form-stack section-spacing',onSubmit:submit},
        h(Problem,{message:error}),details.length>0&&el('ul',{className:'error-list'},...details.map((item,index)=>el('li',{key:index},typeof item==='object'?`Row ${item.line}: ${item.message}`:item))),
        h(Field,{label:'Student CSV file',name:'file',type:'file',accept:'.csv,text/csv',required:true,onChange:e=>setFile(e.target.files?.[0]||null),hint:'Never import real university records without institutional authorisation.'}),
        h(FormActions,null,h(Link,{to:'/students',className:'button button-outline'},'Cancel'),h(Button,{type:'submit',busy,disabled:!file},'Validate and import')))));
}

function CameraReader({onDetected}) {
  const [active,setActive]=useState(false),[cameraId,setCameraId]=useState('');
  const [cameras,setCameras]=useState([]),[message,setMessage]=useState('Camera is off.'),[fatal,setFatal]=useState('');
  const onDetectedRef=useRef(onDetected);
  useEffect(()=>{onDetectedRef.current=onDetected;},[onDetected]);
  useEffect(()=>{
    if(!active)return;
    let cancelled=false, scanner=null, completed=false;
    setFatal('');setMessage('Starting the camera…');
    async function start(){
      try{
        const mod=await import('html5-qrcode');
        if(cancelled)return;
        scanner=new mod.Html5Qrcode('qr-reader',{verbose:false});
        const found=async (code)=>{
          if(completed||cancelled)return;
          completed=true;setMessage('QR code scanned. Verifying…');
          await scanner.stop().catch(()=>{});
          if(!cancelled){setActive(false);onDetectedRef.current(code.trim());}
        };
        const options={fps:12,qrbox:(width,height)=>({width:Math.min(250,width-20),height:Math.min(250,height-20)}),aspectRatio:1};
        const attempts=cameraId ? [cameraId] : [{facingMode:{exact:'environment'}},{facingMode:'environment'}];
        let started=false;
        for (const id of attempts){
          try{await scanner.start(id,options,found,()=>{});started=true;break;}catch(e){if(cancelled)break;}
        }
        if(!started&&!cancelled){
          const devices=await mod.Html5Qrcode.getCameras();
          const back=devices.find(c=>/back|rear|environment/i.test(c.label))||devices[devices.length-1];
          if(back){await scanner.start(back.id,options,found,()=>{});started=true;}
        }
        if(cancelled){if(started)await scanner.stop().catch(()=>{});return;}
        const devices=await mod.Html5Qrcode.getCameras().catch(()=>[]);
        setCameras(devices);setMessage(started?'Camera ready. Point it at a QR code.':'No camera available. Use manual entry.');
      }catch(e){if(!cancelled){setFatal('Camera could not start. Allow camera permission, switch cameras, or verify manually.');setMessage('Camera unavailable.');}}
    }
    start();
    return()=>{cancelled=true;if(scanner){try{Promise.resolve(scanner.stop()).catch(()=>{}).finally(()=>{try{scanner.clear().catch(()=>{});}catch(e){}});}catch(e){try{scanner.clear().catch(()=>{});}catch(e2){}}}};
  },[active,cameraId]);
  return h(Panel,{className:'camera-panel'},
    el('h2',null,'Scan with your camera'),
    el('p',{className:'muted'},'On a phone, the rear-facing camera is selected first. Your browser may ask for camera permission.'),
    el('div',{id:'qr-reader',className:'reader','aria-label':'QR camera preview'}),
    el('p',{className:'hint',role:'status','aria-live':'polite'},message),h(Problem,{message:fatal}),
    cameras.length>1&&h(Field,{select:true,name:'camera',label:'Choose camera',value:cameraId,onChange:e=>{setActive(false);setCameraId(e.target.value);setMessage('Camera selected. Tap Start camera to use it.');},choices:cameras.map((c,i)=>({value:c.id,label:c.label||`Camera ${i+1}`}))}),
    h(Button,{variant:active?'outline':'primary',onClick:()=>setActive(s=>!s)},active?'Stop camera':'Start camera'),
    el('p',{className:'hint'},'Scanning uses the secure browser camera interface. Camera images are not uploaded to this application.'));
}
export function Verify() {
  const [token,setToken]=useState(''),[result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const onScan=async (code)=>{setToken(code);await check(code);};
  async function check(value){setError('');setResult(null);if(!value.trim()){setError('Enter a QR token.');return;}
    setBusy(true);try{setResult(await api('/verify',{method:'POST',body:{token:value.trim()}}));}catch(e){setError(e.message);}finally{setBusy(false);}}
  return group(h(TitleBlock,{eyebrow:'Identity verification',title:'Verify student ID',description:'Scan a QR code or enter a code to check the current record status.'}),
    el('div',{className:'two-col'},h(CameraReader,{onDetected:onScan}),h(Panel,null,
      el('h2',null,'Manual verification'),el('p',{className:'muted'},'Use this when camera access is unavailable.'),
      el('form',{onSubmit:e=>{e.preventDefault();check(token);},className:'form-stack'},
        h(Field,{label:'QR token',name:'token',value:token,onChange:e=>setToken(e.target.value),autoComplete:'off',required:true,placeholder:'Paste scanned code here'}),
        h(Button,{type:'submit',busy},'Verify identity')),
      h(Problem,{message:error}),result&&el('div',{className:'verification-result',role:'status','aria-live':'polite'},
        el('div',{className:'result-head'},el('h3',null,'Verification result'),h(Pill,{status:result.outcome})),
        el('p',null,result.message),
        result.student&&el('div',{className:'result-student'},
          result.student.photo_url&&el('img',{src:result.student.photo_url,alt:'Student record photograph',className:'profile-image',referrerPolicy:'no-referrer'}),
          el('div',null,el('strong',null,result.student.name),el('p',null,result.student.matric_no),el('p',null,`${result.student.department} · ${result.student.level} level`),
            h(Link,{to:'/students/'+result.student.id,className:'text-link'},'View student record'))),
        el('p',{className:'notice'},'Check the person’s identity independently. A copied QR code is not proof that its holder is the student.')))));
}
export function Requests() {
  const {inform}=useAuth();const {value,loading,error,reload}=useResource('/registration-requests');
  const [busy,setBusy]=useState(0),[actionError,setActionError]=useState('');
  async function decide(id,choice){setBusy(id);setActionError('');try{const result=await api('/registration-requests/'+id+'/'+choice,{method:'POST',body:{}});inform(result.message);reload();}
    catch(e){setActionError(e.message);}finally{setBusy(0);}}
  return group(h(TitleBlock,{eyebrow:'Account access',title:'Registration requests',description:'Review student requests before granting account access.'}),h(Problem,{message:error||actionError}),
    loading?h(Spinner):value?.items?.length?el('div',{className:'cards-list'},...value.items.map(r=>h(Panel,{key:r.id},
      el('div',{className:'request-row'},el('div',null,el('h2',null,r.name),el('p',null,r.matric_no+' · '+r.department),el('p',{className:'hint'},'Requested '+compactDate(r.requested_at))),
        el('div',{className:'actions'},h(Button,{variant:'outline',busy:busy===r.id,onClick:()=>decide(r.id,'reject')},'Reject'),
          h(ConfirmAction,{title:'Approve student account?',text:`You are about to grant account access for ${r.matric_no}. Confirm this is the authorised student.`,busy:busy===r.id,action:()=>decide(r.id,'approve')},'Approve'))))))
        :h(Empty,{title:'No pending requests',text:'All current student account requests have been reviewed.'}));
}
export function EventLogs({audit=false}) {
  const {value,loading,error}=useResource(audit?'/admin-audit':'/logs');
  return group(h(TitleBlock,{eyebrow:audit?'Accountability':'Verification',title:audit?'Admin audit':'Verification history',
     description:audit?'An administrative record of important changes.':'Recent QR verification outcomes. Raw QR secrets are never displayed.'}),
    h(Problem,{message:error}),loading?h(Spinner):value?.items?.length ? h(Panel,null,
      el('div',{className:'table-scroll'},el('table',null,
        audit?el('thead',null,el('tr',null,...['Action','Details','Administrator','Time'].map(x=>el('th',{key:x,scope:'col'},x))))
        :el('thead',null,el('tr',null,...['Outcome','Student','Verifier','Time'].map(x=>el('th',{key:x,scope:'col'},x)))),
        el('tbody',null,...value.items.map(item=>el('tr',{key:item.id},
          audit?group(el('td',null,item.event.replaceAll('_',' ')),el('td',null,item.details),el('td',null,item.actor||'System'),el('td',null,compactDate(item.created_at)))
           :group(el('td',null,h(Pill,{status:item.result})),el('td',null,item.matric_no||'Unknown / invalid code'),el('td',null,item.verified_by_name||'—'),el('td',null,compactDate(item.verified_at)))))))))
      :h(Empty,{title:'No events recorded',text:'New events will appear here after authorised activity.'}));
}
export function StudentAccount() {
  const {value,loading,error}=useResource('/student/me');const s=value?.student;
  return group(h(TitleBlock,{eyebrow:'My account',title:'My student card',description:'Show your unique code to an authorised verifier when requested.',
    actions:h(Link,{className:'button button-outline',to:'/account/password'},'Change password')}),h(Problem,{message:error}),
    loading?h(Spinner):s&&el('div',{className:'two-col'},
      h(Panel,null,el('h2',null,s.name),h(Pill,{status:s.status}),el('dl',{className:'detail-list'},
        h(DetailRow,{label:'Matriculation number',value:s.matric_no}),h(DetailRow,{label:'Faculty',value:s.faculty}),
        h(DetailRow,{label:'Department',value:s.department}),h(DetailRow,{label:'Level',value:s.level}))),
      h(Panel,null,el('h2',null,'My QR credential'),s.status==='Active'?
        group(el('img',{src:'/api/student/my-qr.png',alt:'Your unique student QR credential',className:'qr-image'}),
          el('a',{href:'/api/student/my-qr.png',className:'button button-primary',download:true},'Download my QR code')):
        el('p',{className:'notice'},'Your QR credential is unavailable while your record is inactive.'),
        el('p',{className:'hint'},'Protect this QR code. A verifier should still check your identity.'))));
}
export function Password() {
  const [d,setD]=useState({current_password:'',new_password:'',confirm:''});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[success,setSuccess]=useState('');
  async function submit(e){e.preventDefault();setError('');setSuccess('');if(d.new_password!==d.confirm){setError('The passwords do not match.');return;}
    setBusy(true);try{const r=await api('/account/password',{method:'POST',body:d});setSuccess(r.message);setD({current_password:'',new_password:'',confirm:''});}
    catch(ex){setError(ex.message);}finally{setBusy(false);}}
  return group(h(TitleBlock,{eyebrow:'Account security',title:'Change password',description:'Use a strong, unique password containing at least 12 characters.'}),
    h(Panel,{className:'form-panel'},el('form',{onSubmit:submit,className:'form-stack'},h(Problem,{message:error}),
      success&&el('p',{className:'alert alert-success',role:'status'},success),
      h(Field,{label:'Current password',name:'current_password',type:'password',autoComplete:'current-password',required:true,value:d.current_password,onChange:getInput(setD,'current_password')}),
      h(Field,{label:'New password',name:'new_password',type:'password',required:true,minLength:12,maxLength:128,autoComplete:'new-password',value:d.new_password,onChange:getInput(setD,'new_password')}),
      h(Field,{label:'Confirm new password',name:'confirm',type:'password',required:true,autoComplete:'new-password',value:d.confirm,onChange:getInput(setD,'confirm')}),
      h(Button,{type:'submit',busy},'Update password'))));
}
export function Cleanup() {
  const {value,loading,error,reload}=useResource('/students/demo-cleanup');
  const {inform}=useAuth();const [confirmation,setConfirmation]=useState(''),[busy,setBusy]=useState(false),[actionError,setActionError]=useState('');
  async function remove(e){e.preventDefault();setBusy(true);setActionError('');try{const r=await api('/students/demo-cleanup',{method:'POST',body:{confirmation}});inform(r.message);setConfirmation('');reload();}catch(ex){setActionError(ex.message);}finally{setBusy(false);}}
  return group(h(TitleBlock,{eyebrow:'Maintenance',title:'Remove DEMO records',description:'Remove only records with the known DEMO/2026 matriculation prefix and synthetic source flag.'}),
    h(Panel,{className:'form-panel'},h(Problem,{message:error||actionError}),loading?h(Spinner):group(
      el('p',null,el('strong',null,(value?.count??'—')+' matching synthetic records'), ' will be deleted. Other student records are not selected.'),
      el('p',{className:'notice'},'Deletion cannot be undone. The associated accounts and requests will be removed; verification history will be retained without student links.'),
      el('form',{onSubmit:remove,className:'form-stack'},h(Field,{label:'Type DELETE DEMO RECORDS to confirm',name:'confirmation',value:confirmation,onChange:e=>setConfirmation(e.target.value),required:true,autoComplete:'off'}),
       h(Button,{type:'submit',variant:'danger',busy,disabled:value?.count===0||confirmation!=='DELETE DEMO RECORDS'},'Delete matching test records')))));
}
export function Missing() {return el('div',{className:'center-block'},el('h1',null,'Page not found'),el('p',null,'The page you requested does not exist.'),h(Link,{to:'/',className:'button button-primary'},'Go to homepage'));}
