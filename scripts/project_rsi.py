#!/usr/bin/env python3
"""Approval-gated project learning for multiple coding harnesses (Python 3.9+)."""
import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_adapters import CONFIG, policy_for, profiles, detect, skill_name, target_kind

LIMIT=24*1024
CHOICES={'approve','reject','change','explain'}
MDC_HEADER=b'---\ndescription: Project RSI learned project lessons\nalwaysApply: true\n---\n'

def digest(data): return hashlib.sha256(data).hexdigest()
def read_json(path): return json.loads(path.read_text(encoding='utf-8'))
def encoded(value): return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def atomic(path,data):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.rsi-',dir=path.parent)
    try:
        mode=(path.stat().st_mode & 0o777) if path.exists() else 0o600
        if hasattr(os,'fchmod'):os.fchmod(fd,mode)
        else:os.chmod(temp,mode)
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def inside(base,relative):
    p=Path(relative)
    if p.is_absolute() or '..' in p.parts:raise ValueError('contained relative path required')
    full=base/p
    for current in [full,*full.parents]:
        if current==base.parent:break
        if current.is_symlink():raise ValueError('symlink rejected')
    if not full.resolve().is_relative_to(base.resolve()):raise ValueError('path escape')
    return full

def bounded(path):
    b=path.read_bytes()
    if len(b)>LIMIT:raise ValueError('Markdown exceeds 24 KiB')
    return b

def lesson(text,marker):
    if not re.fullmatch('[A-Z][A-Z0-9_]{1,63}',marker):raise ValueError('invalid lesson marker')
    begin=f'<!-- {marker}_BEGIN -->';end=f'<!-- {marker}_END -->'
    if not text.count(begin) and not text.count(end):return None,begin,end
    if text.count(begin)!=1 or text.count(end)!=1:raise ValueError('one lesson marker pair required')
    prefix,rest=text.split(begin);body,suffix=rest.split(end)
    return body,begin,end

def validate_candidate(path,data,policy=None):
    if path.endswith('/SKILL.md'):
        header=re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)',data.decode(),re.S)
        if not header:raise ValueError('skill frontmatter required')
        name=re.search(r'^name:\s*([a-z0-9-]+)\s*$',header[1],re.M)
        if not name or name[1]!=skill_name(path,policy or policy_for('codex')):raise ValueError('skill name must match directory')
        if not re.search(r'^description:\s*\S.+$',header[1],re.M):raise ValueError('skill description required')

def probe_ok(path):
    p=read_json(path)
    if p.get('level') not in {'STATIC','STATIC_SCENARIO','OFFLINE_SYNTHETIC'}:raise ValueError('probe level required')
    checks=p.get('checks',[])
    if not checks or not all(x.get('name') and x.get('passed') is True and x.get('evidence') for x in checks):raise ValueError('all concrete probe checks must pass')
    return p

def check_session(expected,transport,session_id=None):
    actual=os.environ.get('CODEX_THREAD_ID') if transport=='native' else (session_id or os.environ.get('PROJECT_RSI_SESSION_ID'))
    if not actual or actual!=expected:raise ValueError('current conversation/session mismatch; pass --session-id for local transport')

def build(plan_path,output,session_id=None):
    plan_path=plan_path.resolve();run=plan_path.parent;plan=read_json(plan_path)
    if (run/'manifest.json').exists():raise ValueError('frozen manifest exists; reuse its form or create a new run')
    if plan.get('schema')!=1 or not plan.get('items') or not plan.get('thread_id'):raise ValueError('plan identity/items required')
    root=Path(plan['project_root']).resolve(strict=True)
    config_path=inside(root,CONFIG)
    config=read_json(config_path) if config_path.exists() else {}
    name=plan.get('harness',config.get('harness','codex'))
    policy=policy_for(name,plan.get('instruction_files',config.get('instruction_files')),plan.get('skill_roots',config.get('skill_roots')))
    transport=plan.get('transport',config.get('transport',policy['transport']))
    if transport not in {'native','local'}:raise ValueError('transport must be native or local')
    check_session(plan['thread_id'],transport,session_id)
    fixture_path=inside(root,'.project-rsi-fixture.json')
    if plan.get('test_mode'):
        if not fixture_path.exists() or read_json(fixture_path)!={'synthetic':True,'project_root':str(root)}:
            raise ValueError('test_mode requires an explicitly isolated synthetic fixture marker')
    resolved_output=output.resolve()
    if resolved_output.is_relative_to(root):
        rel=resolved_output.relative_to(root).as_posix()
        if rel in policy['instruction_files'] or any(rel.startswith(p+'/') for p in policy['skill_roots']):
            raise ValueError('review output cannot overwrite active instructions or skills')
    review=inside(run,plan['review_file']);review_data=bounded(review)
    seen=set();ordinary=set();items=[];view=[];total=0
    for item in plan['items']:
        if not re.fullmatch('[A-Za-z0-9_-]{1,48}',item['id']) or item['id'] in seen:raise ValueError('unique ASCII item ID required')
        seen.add(item['id'])
        if not all(item.get(k) for k in ['title','summary','impact','evidence','changes']):raise ValueError('readable rationale and evidence required')
        if not isinstance(item['evidence'],list) or not all(isinstance(x,str) for x in item['evidence']) or not isinstance(item['changes'],list):raise ValueError('evidence and changes must be lists')
        record={k:item[k] for k in ['id','title','summary','impact','evidence']};record['changes']=[]
        display={**record,'changes':[]}
        item_paths=set()
        for change in item['changes']:
            c=dict(change);kind=target_kind(c['path'],c['operation'],policy);target=inside(root,c['path'])
            if c['path'] in item_paths:raise ValueError('one change per item/target required')
            item_paths.add(c['path'])
            old=bounded(target) if target.exists() else None
            candidate=inside(run,c['candidate']);new=bounded(candidate)
            if not new.strip():raise ValueError('empty candidate')
            if c['operation']=='write':validate_candidate(c['path'],new,policy)
            probe_path=inside(run,c['probe']);probe=probe_ok(probe_path)
            c.update(kind=kind,candidate_sha256=digest(new),probe_sha256=digest(probe_path.read_bytes()),expected_sha256=digest(old) if old is not None else None)
            if c['operation']=='append_lesson':
                body,begin,end=lesson((old or b'').decode(),c.get('marker','PROJECT_RSI_LESSONS'))
                if begin in new.decode() or end in new.decode():raise ValueError('lesson candidate must not contain section markers')
                c['expected_section_sha256']=digest(body.encode()) if body is not None else None
            else:
                if c['path'] in ordinary:raise ValueError('ordinary file appears in more than one item')
                ordinary.add(c['path'])
            record['changes'].append(c)
            preview=(MDC_HEADER+new).decode() if c['path'].endswith('.mdc') and old is None else new.decode()
            display['changes'].append({**c,'candidate_text':preview,'before':(old or b'').decode() or '(new file)','probe_summary':probe['level']+' · '+str(len(probe['checks']))+' checks passed'})
            total+=len(new)+len(old or b'')
        items.append(record);view.append(display)
    manifest={'schema':1,'form_id':plan['form_id'],'project_root':str(root),'thread_id':plan['thread_id'],'plan_file':plan_path.name,'plan_sha256':digest(plan_path.read_bytes()),'review_file':plan['review_file'],'review_sha256':digest(review_data),'created_at':datetime.now(timezone.utc).isoformat(),'items':items,'test_mode':bool(plan.get('test_mode')),'transport':transport,'target_policy':policy}
    if config:manifest['config_sha256']=digest(config_path.read_bytes())
    if plan.get('test_mode'):manifest['fixture_sha256']=digest(fixture_path.read_bytes())
    if plan.get('application_adapter'):
        adapter=plan['application_adapter']
        adapter_path=inside(run,adapter['plan'])
        manifest['application_adapter']={'plan':adapter['plan'],'sha256':digest(adapter_path.read_bytes())}
    atomic(run/'manifest.json',encoded(manifest))
    spec={'form_id':plan['form_id'],'run':str(run),'manifest_sha256':digest((run/'manifest.json').read_bytes()),'submission_id':str(uuid.uuid4()),'items':view,'test_mode':manifest['test_mode'],'transport':transport,'harness':name}
    if manifest['test_mode'] and plan.get('test_choices'):
        spec.update(test_choices=plan['test_choices'],test_note=plan.get('test_note',''))
    template=(Path(__file__).resolve().parent.parent/'assets/confirmation.html').read_text()
    safe=json.dumps(spec,ensure_ascii=False).replace('</','<\\/')
    fragment=template.replace('__RSI_ROOT_ID__','project-rsi-'+digest(plan['form_id'].encode())[:12]).replace('__RSI_FORM_JSON__',safe)
    atomic(output,fragment.encode());atomic(run/'form-binding.json',encoded({'output':str(output),'sha256':digest(fragment.encode()),'spec':spec}))
    return {'status':'AWAITING_USER_CONFIRMATION','manifest':str(run/'manifest.json'),'form':str(output),'active_targets_written':0}

@contextmanager
def run_lock(run):
    lock=run/'.consume.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise ValueError('run already processing; if a prior process crashed, inspect receipts before removing .consume.lock')
    try:
        with os.fdopen(fd,'w') as f:f.write(str(os.getpid()))
        yield
    finally:lock.unlink()

def consume(run,submission_path,confirmation_reference,session_id=None):
    run=run.resolve()
    with run_lock(run):return _consume(run,submission_path,confirmation_reference,session_id)

def _consume(run,submission_path,confirmation_reference,session_id=None):
    run=run.resolve();data=submission_path.read_bytes()
    if len(data)>16*1024:raise ValueError('submission exceeds 16 KiB')
    s=json.loads(data);manifest_path=run/'manifest.json';m=read_json(manifest_path)
    if s.get('schema')!=1 or m.get('schema')!=1:raise ValueError('unsupported schema')
    if not confirmation_reference.strip():raise ValueError('actual confirmation reference required')
    check_session(m['thread_id'],m.get('transport','native'),session_id)
    if s.get('run')!=str(run) or s.get('form_id')!=m['form_id'] or s.get('manifest_sha256')!=digest(manifest_path.read_bytes()):raise ValueError('form/run/version binding mismatch')
    if m.get('application_adapter'):raise ValueError('project-specific application guard required; generic consume cannot bypass it')
    UUID=uuid.UUID(s['submission_id']);submission_id=str(UUID)
    receipts=run/'receipts';receipt_path=receipts/(submission_id+'.json')
    if receipt_path.exists():
        prior=read_json(receipt_path)
        if prior['submission_sha256']!=digest(data):raise ValueError('submission ID reused with different content')
        return {**prior,'duplicate':True}
    if digest(inside(run,m['plan_file']).read_bytes())!=m['plan_sha256'] or digest(inside(run,m['review_file']).read_bytes())!=m['review_sha256']:raise ValueError('reviewed source changed')
    answers=s.get('answers',[])
    if len(answers)!=len(m['items']) or {a.get('id') for a in answers}!={i['id'] for i in m['items']}:raise ValueError('one answer per item required')
    by_id={a['id']:a for a in answers}
    for a in answers:
        if a.get('value') not in CHOICES or not isinstance(a.get('comment'),str):raise ValueError('invalid choice/comment')
        if a['value'] in {'change','explain'} and not a['comment'].strip():raise ValueError('comment required')
    root=Path(m['project_root']).resolve(strict=True);pending={};dispositions=[]
    if m.get('config_sha256') and digest(inside(root,CONFIG).read_bytes())!=m['config_sha256']:raise ValueError('harness configuration changed')
    if m.get('test_mode'):
        fixture_path=inside(root,'.project-rsi-fixture.json')
        if not m.get('fixture_sha256') or digest(fixture_path.read_bytes())!=m['fixture_sha256'] or read_json(fixture_path)!={'synthetic':True,'project_root':str(root)}:
            raise ValueError('synthetic fixture identity changed')
    policy=m.get('target_policy',policy_for('codex'))
    for item in m['items']:
        a=by_id[item['id']];status={'reject':'REJECTED','change':'REVISION_REQUESTED','explain':'EXPLANATION_REQUESTED','approve':'APPROVED'}[a['value']]
        disposition={'id':item['id'],'title':item['title'],'decision':status,'comment':a['comment'],'changes':[]};dispositions.append(disposition)
        if status!='APPROVED':continue
        if a['comment'].strip():disposition['decision']='APPROVAL_NOTES_NEED_INTERPRETATION';continue
        proposed=[]
        try:
            for c in item['changes']:
                if target_kind(c['path'],c['operation'],policy)!=c['kind']:raise ValueError('target kind mismatch')
                candidate=inside(run,c['candidate']);probe=inside(run,c['probe'])
                new=bounded(candidate)
                if digest(new)!=c['candidate_sha256'] or digest(probe.read_bytes())!=c['probe_sha256']:raise ValueError('candidate/probe changed')
                probe_ok(probe);target=inside(root,c['path']);old=bounded(target) if target.exists() else None
                if c['operation']=='write':
                    if (digest(old) if old is not None else None)!=c['expected_sha256']:raise ValueError('target version conflict')
                    validate_candidate(c['path'],new,policy)
                else:
                    original=(old or b'').decode();body,begin,end=lesson(original,c.get('marker','PROJECT_RSI_LESSONS'))
                    if (digest(body.encode()) if body is not None else None)!=c['expected_section_sha256']:raise ValueError('lesson section changed')
                    initial=old or (MDC_HEADER if c['path'].endswith('.mdc') else b'')
                    base=pending.get(c['path'],{}).get('new',initial).decode()
                    addition=new.decode().strip()+'\n'
                    composed_body,begin,end=lesson(base,c.get('marker','PROJECT_RSI_LESSONS'))
                    if composed_body is None:new=(base.rstrip()+'\n\n'+begin+'\n'+addition+end+'\n').encode()
                    else:new=base.replace(end,addition+end).encode()
                if len(new)>LIMIT:raise ValueError('result exceeds 24 KiB')
                proposed.append((c,target,old,new))
        except (ValueError,OSError) as e:
            disposition['decision']='DEFERRED_CONFLICT';disposition['reason']=str(e);continue
        for c,target,old,new in proposed:
            existing=pending.get(c['path'])
            pending[c['path']]={'path':c['path'],'kind':c['kind'],'target':target,'old':existing['old'] if existing else old,'new':new,'items':(existing['items'] if existing else [])+[item['id']]}
    receipt={'schema':1,'form_id':m['form_id'],'submission_id':submission_id,'thread_id':m['thread_id'],'confirmation_reference':confirmation_reference,'submission_sha256':digest(data),'manifest_sha256':s['manifest_sha256'],'status':'PREPARED','items':dispositions,'changes':[],'planned':[],'behavioral_effect':'NOT_VERIFIED','test_mode':bool(m.get('test_mode')),'project_root':str(root),'harness':policy.get('harness','codex')}
    backup_dir=receipts/(submission_id+'-files')
    for index,p in enumerate(pending.values()):
        receipt['planned'].append({'path':p['path'],'before_sha256':digest(p['old']) if p['old'] is not None else None,'after_sha256':digest(p['new']),'backup':str(backup_dir/(str(index)+'-before.md')) if p['old'] is not None else None})
    atomic(receipt_path,encoded(receipt))
    try:
        for index,p in enumerate(pending.values()):
            current=p['target'].read_bytes() if p['target'].exists() else None
            if current!=p['old']:raise ValueError('concurrent target change: '+p['path'])
            if p['old'] is not None:atomic(backup_dir/(str(index)+'-before.md'),p['old'])
            diff=''.join(difflib.unified_diff((p['old'] or b'').decode().splitlines(True),p['new'].decode().splitlines(True),fromfile=p['path']+':before',tofile=p['path']+':after'))
            diff_path=backup_dir/(str(index)+'.diff');atomic(diff_path,diff.encode())
            atomic(p['target'],p['new'])
            if p['target'].read_bytes()!=p['new']:raise ValueError('readback mismatch')
            change={'path':p['path'],'kind':p['kind'],'item_ids':p['items'],'before_sha256':digest(p['old']) if p['old'] is not None else None,'after_sha256':digest(p['new']),'diff':str(diff_path)}
            receipt['changes'].append(change)
            for d in dispositions:
                if d['id'] in p['items']:d['changes'].append(p['path'])
            atomic(receipt_path,encoded(receipt))
        for d in dispositions:
            if d['decision']=='APPROVED':d['decision']='ADOPTED_STATIC_ONLY'
        receipt['status']='ADOPTED_STATIC_ONLY' if receipt['changes'] else 'DECISIONS_RECORDED'
    except (ValueError,OSError) as e:
        receipt['status']='PARTIAL_OR_CONFLICT';receipt['error']=str(e)
    atomic(receipt_path,encoded(receipt));atomic(run/'latest-receipt.json',encoded(receipt))
    return receipt

def initialize(root,harness='auto',instruction_files=None,skill_roots=None,transport=None,install_skill=False):
    root=root.resolve(strict=True)
    name=detect(root) if harness=='auto' else harness
    if instruction_files is None:
        if name=='codex' and (root/'AGENTS.override.md').exists():instruction_files=['AGENTS.override.md']
        elif name=='claude' and not (root/'CLAUDE.md').exists() and (root/'.claude/CLAUDE.md').exists():instruction_files=['.claude/CLAUDE.md']
        elif name=='opencode' and not (root/'AGENTS.md').exists() and (root/'CLAUDE.md').exists():instruction_files=['CLAUDE.md']
        elif name=='dsh' and not (root/'AGENTS.md').exists() and (root/'CLAUDE.md').exists():instruction_files=['CLAUDE.md']
        elif name=='workbuddy' and not (root/'CODEBUDDY.md').exists():
            if (root/'.codebuddy/CODEBUDDY.md').exists():instruction_files=['.codebuddy/CODEBUDDY.md']
            elif (root/'AGENTS.md').exists():instruction_files=['AGENTS.md']
    config=policy_for(name,instruction_files,skill_roots)
    config['transport']=transport or config['transport'];config={'schema':1,**config}
    if config['transport'] not in {'native','local'}:raise ValueError('invalid transport')
    path=inside(root,CONFIG)
    for rel in config['instruction_files']+config['skill_roots']:inside(root,rel)
    if path.exists() and read_json(path)!=config:raise ValueError('configuration exists with different settings; review and edit it explicitly')
    destination=inside(root,config['skill_roots'][0]+'/project-rsi')
    source=Path(__file__).resolve().parent.parent
    if install_skill and destination.exists() and destination.resolve()!=source:raise ValueError('skill destination already exists; refusing to overwrite')
    if install_skill and not destination.exists():
        # An allowlist prevents repository metadata, real runs, and local caches being installed.
        for entry in ['SKILL.md','LICENSE','agents','scripts','assets','references']:
            p=source/entry
            if p.is_file():atomic(destination/entry,p.read_bytes())
            elif p.is_dir():
                for file in p.rglob('*'):
                    if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':
                        if file.is_symlink():raise ValueError('symlink in skill source')
                        atomic(destination/file.relative_to(source),file.read_bytes())
    if not path.exists():atomic(path,encoded(config))
    return {'status':'INITIALIZED','config':str(path),'harness':name,'instruction_files':config['instruction_files'],'skill_directory':str(destination) if install_skill else None,'active_instructions_written':0}

def demo(directory,harness='generic'):
    directory=directory.resolve()
    if directory.exists():raise ValueError('demo directory must not exist; never use a real project directory')
    root=directory/'project';run=directory/'run';root.mkdir(parents=True);run.mkdir()
    policy=policy_for(harness);instruction=policy['instruction_files'][0]
    atomic(root/'.project-rsi-fixture.json',encoded({'synthetic':True,'project_root':str(root)}))
    if not instruction.endswith('.mdc'):atomic(inside(root,instruction),b'# Synthetic project\n\nPreserve these original instructions.\n')
    atomic(run/'review.md',b'# Isolated review\nAll proposals are synthetic. No real project is targeted.\n')
    atomic(run/'lesson.md',b'- Verify the full result before reporting completion.\n')
    atomic(run/'probe.json',encoded({'level':'OFFLINE_SYNTHETIC','checks':[{'name':'isolated target boundary','passed':True,'evidence':'all targets are inside a newly created synthetic fixture'}]}))
    items=[]
    for ident,title,summary,path,op,candidate in [
        ('A1','Approve a small lesson','Adds one lesson to the synthetic project instructions.',instruction,'append_lesson','lesson.md'),
        ('R1','Reject a proposed skill','Choose reject to verify that this sample skill is not created.',policy['skill_roots'][0]+'/learned-rejected/SKILL.md','write','rejected.md'),
        ('C1','Request changes with a note','Write a long multiline note; this sample skill must remain unmodified.',policy['skill_roots'][0]+'/learned-revised/SKILL.md','write','revised.md')]:
        if op=='write':atomic(run/candidate,('---\nname: '+Path(path).parent.name+'\ndescription: Synthetic example only.\n---\nPreserve the project scope.\n').encode())
        items.append({'id':ident,'title':title,'summary':summary,'impact':'Isolated demonstration only. No real project files.','evidence':['synthetic fixture generated by the demo command'],'changes':[{'path':path,'operation':op,'candidate':candidate,'probe':'probe.json'}]})
    session='local-'+str(uuid.uuid4())
    plan={'schema':1,'form_id':'demo-'+str(uuid.uuid4()),'project_root':str(root),'thread_id':session,'review_file':'review.md','harness':harness,'transport':'local','items':items,'test_mode':True,'test_choices':{'A1':'approve','R1':'reject','C1':'change'},'test_note':'Please shorten this sample lesson while preserving its scope.\n请保留这条多行备注，调整方案后再次确认。'}
    atomic(run/'plan.json',encoded(plan));result=build(run/'plan.json',run/'form.html',session)
    result.update(run=str(run),fixture_project=str(root),session_id=session,test_mode=True)
    atomic(directory/'demo.json',encoded(result));return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('build');p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--session-id')
    p=sub.add_parser('consume');p.add_argument('--run',type=Path,required=True);p.add_argument('--submission',type=Path,required=True);p.add_argument('--confirmation-reference',required=True)
    p.add_argument('--session-id')
    p=sub.add_parser('profiles')
    p=sub.add_parser('init');p.add_argument('--project',type=Path,required=True);p.add_argument('--harness',choices=['auto',*profiles()],default='auto');p.add_argument('--instructions',action='append');p.add_argument('--skill-root',action='append');p.add_argument('--transport',choices=['native','local']);p.add_argument('--install-skill',action='store_true')
    p=sub.add_parser('demo');p.add_argument('--directory',type=Path,required=True);p.add_argument('--harness',choices=list(profiles()),default='generic')
    a=parser.parse_args()
    if a.command=='build':result=build(a.plan,a.output,a.session_id)
    elif a.command=='consume':result=consume(a.run,a.submission,a.confirmation_reference,a.session_id)
    elif a.command=='init':result=initialize(a.project,a.harness,a.instructions,a.skill_root,a.transport,a.install_skill)
    elif a.command=='demo':result=demo(a.directory,a.harness)
    else:result=profiles()
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
