"""Evaluator and target custodian. Never imported by the fitting program."""
from pathlib import Path
import argparse, hashlib, json, shutil, time, secrets
from numbers import Real
import numpy as np
from recovery import RenderClient, BOUNDS, DEFAULT_PARAMETERS, PARAMETER_NAMES

ROOT = Path(__file__).resolve().parent

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rmse(a, b):
    if a.shape != b.shape:
        raise ValueError(f'shape mismatch: {a.shape} != {b.shape}')
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('RMSE input contains non-finite values')
    return float(np.sqrt(np.mean((a.astype(float)-b.astype(float))**2)))

def improvement(baseline, candidate, threshold=.50):
    """Return an explicit improvement result; zero baselines never pass."""
    if not np.isfinite([baseline, candidate]).all():
        return {'reduction':None, 'pass':False, 'failure':'non-finite RMSE'}
    if baseline <= 0:
        return {'reduction':None, 'pass':False, 'failure':'non-positive baseline RMSE'}
    reduction = float(1.0 - candidate / baseline)
    return {'reduction':reduction, 'pass':bool(reduction >= threshold)}

def validate_recovered(parameters):
    if not isinstance(parameters, dict):
        return 'best_parameters is missing or not an object'
    for key in PARAMETER_NAMES:
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, Real):
            return f'{key} is missing or non-numeric'
        value = float(value)
        lo, hi = BOUNDS[key]
        if not np.isfinite(value) or not lo <= value <= hi:
            return f'{key} is outside its declared bounds'
    return None

def render(client, p, name, width, height, samples, seed, shift=0):
    result = client.render(p, case_name=name, width=width, height=height,
                           samples=samples, seed=seed, camera_shift=shift)
    return np.load(result.array_path), result

def copy_result(result, directory, name):
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(result.array_path, directory / (name+'.npy'))
    if result.png_path:
        shutil.copyfile(result.png_path, directory / (name+'.png'))

def calibration(args, client):
    out=ROOT/'development'
    base, result=render(client, DEFAULT_PARAMETERS, 'dev-default', args.width,args.height,args.samples,args.seed)
    copy_result(result,out,'default')
    repeat, second=render(client, DEFAULT_PARAMETERS,'dev-repeat',args.width,args.height,args.samples,args.seed)
    checks={'same_seed':{'identical':bool(np.array_equal(base,repeat)), 'rmse':rmse(base,repeat),
                         'max_abs':float(np.max(np.abs(base-repeat)))},'sensitivity':{}}
    for key,(lo,hi) in BOUNDS.items():
        p=dict(DEFAULT_PARAMETERS); p[key] += .15*(hi-lo)
        value, receipt=render(client,p,'dev-'+key,args.width,args.height,args.samples,args.seed)
        copy_result(receipt,out,key)
        checks['sensitivity'][key]={'delta':p[key]-DEFAULT_PARAMETERS[key], 'rmse':rmse(base,value),
                                    'runtime_seconds':receipt.metadata['runtime_seconds']}
    checks['render_settings']={'width':args.width,'height':args.height,'samples':args.samples,'seed':args.seed}
    checks['finite']=bool(np.isfinite(base).all())
    save(out/'CALIBRATION.json',checks)
    print(json.dumps(checks,indent=2),flush=True)

def prepare(args, client):
    custody=ROOT/'evaluation-private'; targets=ROOT/'targets'
    if (custody/'truth.json').exists() or targets.exists():
        raise RuntimeError('Test targets already exist; preserve first attempt and use a new explicitly named experiment.')
    calibration_data=json.loads((ROOT/'development/CALIBRATION.json').read_text())
    if not calibration_data['finite'] or any(x['rmse'] <= 1e-6 for x in calibration_data['sensitivity'].values()):
        raise RuntimeError('Finite-output/sensitivity calibration failed.')
    if calibration_data['same_seed']['rmse'] > 1e-4:
        raise RuntimeError('Same-seed replay RMSE exceeds the declared 1e-4 tolerance.')
    files=['scene.py','recovery.py','render_service.py','evaluate.py','PROTOCOL.md']
    freeze={'source_hashes':{f:sha(ROOT/f) for f in files},
            'training_settings':{'width':args.width,'height':args.height,'samples':args.samples,'seed':args.seed},
            'fit_budget':70,'parameter_range_error_limit':.08,'rmse_reduction_required':.50,
            'withholding':'Labels withheld from fitting inputs on shared filesystem; not a security sandbox.',
            'created_unix':time.time()}
    save(ROOT/'FREEZE.json',freeze)
    rng=secrets.SystemRandom()
    truth={}
    for i in range(3):
        case='case-'+chr(65+i)
        # Draw an interior setting separated from the baseline in at least two coordinates.
        while True:
            p={key:lo+(hi-lo)*rng.uniform(.12,.88) for key,(lo,hi) in BOUNDS.items()}
            distances=[abs(p[k]-DEFAULT_PARAMETERS[k])/(BOUNDS[k][1]-BOUNDS[k][0]) for k in BOUNDS]
            if sum(d>.12 for d in distances)>=2: break
        truth[case]=p
    save(custody/'truth.json',truth)
    targets.mkdir()
    for case,p in truth.items():
        _, result=render(client,p,case+'-target',args.width,args.height,args.samples,args.seed)
        shutil.copyfile(result.array_path, targets/(case+'.npy'))
        copy_result(result,ROOT/'review/targets',case)
        print('TARGET READY '+case,flush=True)
    save(ROOT/'TARGET_RECEIPT.json',{'target_hashes':{p.name:sha(p) for p in sorted(targets.glob('*.npy'))},
                                    'truth_commitment':sha(custody/'truth.json')})

def evaluate(args, client):
    freeze=json.loads((ROOT/'FREEZE.json').read_text())
    for name, expected in freeze['source_hashes'].items():
        if sha(ROOT/name)!=expected: raise RuntimeError('Frozen source changed: '+name)
    truth=json.loads((ROOT/'evaluation-private/truth.json').read_text())
    receipt=json.loads((ROOT/'TARGET_RECEIPT.json').read_text())
    if sha(ROOT/'evaluation-private/truth.json') != receipt['truth_commitment']: raise RuntimeError('Truth changed')
    for name, expected in receipt['target_hashes'].items():
        if sha(ROOT/'targets'/name)!=expected: raise RuntimeError('Target changed')
    fit_path = ROOT/'fit/recovered_parameters.json'
    if not fit_path.exists():
        result={'status':'FAIL','failure':'missing fit/recovered_parameters.json','cases':[],
                'negative_control':{'expected':'FAIL','detected':True}}
        save(ROOT/'RESULTS.json',result); print(json.dumps(result,indent=2),flush=True); return
    try:
        fit=json.loads(fit_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        result={'status':'FAIL','failure':f'invalid fit receipt: {exc}','cases':[],
                'negative_control':{'expected':'FAIL','detected':True}}
        save(ROOT/'RESULTS.json',result); print(json.dumps(result,indent=2),flush=True); return
    fit_case_list=fit.get('cases')
    if not isinstance(fit_case_list,list):
        result={'status':'FAIL','failure':'fit receipt has no cases list','cases':[],
                'negative_control':{'expected':'FAIL','detected':True}}
        save(ROOT/'RESULTS.json',result); print(json.dumps(result,indent=2),flush=True); return
    fit_rows={row.get('case'):row for row in fit_case_list if isinstance(row,dict) and row.get('case')}
    results=[]
    ts=freeze['training_settings']
    default,_=render(client,DEFAULT_PARAMETERS,'eval-default-train',ts['width'],ts['height'],ts['samples'],ts['seed'])
    for name,p in truth.items():
        case=fit_rows.get(name)
        if case is None:
            row={'case':name,'case_pass':False,'failure':'missing fit case',
                 'optimizer_status':'missing','evaluations':0,'held_out':[]}
            results.append(row); save(ROOT/'RESULTS.json',{'status':'IN_PROGRESS','cases':results}); print('EVALUATED '+name+' False',flush=True); continue
        if case.get('status') in ('failed','pending'):
            row={'case':name,'case_pass':False,'failure':case.get('failure') or 'fit case failed',
                 'optimizer_status':case.get('status'),'evaluations':case.get('evaluations',0),'held_out':[]}
            results.append(row); save(ROOT/'RESULTS.json',{'status':'IN_PROGRESS','cases':results}); print('EVALUATED '+name+' False',flush=True); continue
        recovered=case.get('best_parameters')
        parameter_failure=validate_recovered(recovered)
        fitted_path=ROOT/'fit/cases'/name/'fit.npy'
        if parameter_failure or not fitted_path.exists():
            failure=parameter_failure or 'missing fit image'
            row={'case':name,'case_pass':False,'failure':failure,
                 'optimizer_status':case.get('status'),'evaluations':case.get('evaluations',0),'held_out':[]}
            results.append(row); save(ROOT/'RESULTS.json',{'status':'IN_PROGRESS','cases':results}); print('EVALUATED '+name+' False',flush=True); continue
        try:
            target=np.load(ROOT/'targets'/(name+'.npy'),allow_pickle=False)
            fitted=np.load(fitted_path,allow_pickle=False)
        except (OSError, ValueError) as exc:
            row={'case':name,'case_pass':False,'failure':f'cannot load fit/target image: {exc}',
                 'optimizer_status':case.get('status'),'evaluations':case.get('evaluations',0),'held_out':[]}
            results.append(row); save(ROOT/'RESULTS.json',{'status':'IN_PROGRESS','cases':results}); print('EVALUATED '+name+' False',flush=True); continue
        if target.shape != fitted.shape or target.ndim != 3 or target.shape[-1] != 3:
            row={'case':name,'case_pass':False,'failure':f'incompatible target/fit image shapes: {target.shape} vs {fitted.shape}',
                 'optimizer_status':case.get('status'),'evaluations':case.get('evaluations',0),'held_out':[]}
            results.append(row); save(ROOT/'RESULTS.json',{'status':'IN_PROGRESS','cases':results}); print('EVALUATED '+name+' False',flush=True); continue
        if not np.isfinite(target).all() or not np.isfinite(fitted).all():
            row={'case':name,'case_pass':False,'failure':'target or fit image contains non-finite values',
                 'optimizer_status':case.get('status'),'evaluations':case.get('evaluations',0),'held_out':[]}
            results.append(row); save(ROOT/'RESULTS.json',{'status':'IN_PROGRESS','cases':results}); print('EVALUATED '+name+' False',flush=True); continue
        err={k:abs(p[k]-recovered[k])/(BOUNDS[k][1]-BOUNDS[k][0]) for k in BOUNDS}
        start=rmse(target,default); end=rmse(target,fitted)
        training_improvement=improvement(start,end)
        row={'case':name,'truth':p,'recovered':recovered,'normalized_parameter_errors':err,
             'parameter_pass':all(v<=.08 for v in err.values()),
             'training':{'baseline_rmse':start,'fit_rmse':end,**training_improvement},
             'optimizer_status':case['status'],'evaluations':case['evaluations'],'held_out':[]}
        for condition in ['new-view','new-view-light-edit']:
            states={'truth':dict(p),'recovered':dict(recovered),'default':dict(DEFAULT_PARAMETERS)}
            if condition.endswith('edit'):
                for value in states.values(): value['key_energy']=6.5
            rendered={}
            for label,params in states.items():
                image,result=render(client,params,name+'-'+condition+'-'+label,args.width,args.height,args.samples,args.seed,.45)
                rendered[label]=image
                copy_result(result,ROOT/'review/held-out',name+'-'+condition+'-'+label)
            initial=rmse(rendered['truth'],rendered['default'])
            residual=rmse(rendered['truth'],rendered['recovered'])
            held_out_improvement=improvement(initial,residual)
            copied=rmse(rendered['truth'],target) if target.shape==rendered['truth'].shape else None
            row['held_out'].append({'condition':condition,'baseline_rmse':initial,'recovered_rmse':residual,
                                    **held_out_improvement,'pixel_copy_rmse':copied})
        row['case_pass']=row['parameter_pass'] and row['training']['pass'] and all(v['pass'] for v in row['held_out'])
        results.append(row)
        save(ROOT/'RESULTS.json',{'status':'IN_PROGRESS','cases':results})
        print('EVALUATED '+name+' '+str(row['case_pass']),flush=True)
    control_cases=[]
    for row in results:
        training=row.get('training')
        if not training:
            control_cases.append({'case':row['case'],'reduction':0.0,'pass':False,'failure':'fit case unavailable'})
            continue
        baseline=training['baseline_rmse']
        control_cases.append({'case':row['case'],'baseline_rmse':baseline,
                              'default_rmse':baseline,**improvement(baseline,baseline)})
    control={'name':'Returning defaults cannot pass the improvement rule','expected':'FAIL',
             'candidate':'fixed default parameters','cases':control_cases,
             'detected':all(not item['pass'] for item in control_cases)}
    result={'status':'PASS' if all(r['case_pass'] for r in results) else 'MIXED_OR_FAIL',
            'question':'Known-scene three-parameter recovery from one rendered view per case',
            'metric_space':'scene-linear float RGB arrays',
            'fit_objective':'log1p RGB multiscale objective; acceptance RMSE is raw full-image scene-linear RGB',
            'cases':results,'negative_control':control,
            'held_out_settings':{'width':args.width,'height':args.height,'samples':args.samples,'seed':args.seed,'camera_shift':.45},
            'limits':['Synthetic images from known renderer; no arbitrary photograph or equation discovery.',
                      'Three settings only; labels withheld by process interface on shared filesystem.',
                      'Aesthetic acceptance remains with the user.']}
    save(ROOT/'RESULTS.json',result)
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['calibrate','prepare','evaluate'])
    parser.add_argument('--queue',default=str(ROOT/'render-queue'))
    parser.add_argument('--width',type=int,default=256); parser.add_argument('--height',type=int,default=144)
    parser.add_argument('--samples',type=int,default=16); parser.add_argument('--seed',type=int,default=13579)
    args=parser.parse_args()
    client=RenderClient(args.queue,timeout=300)
    {'calibrate':calibration,'prepare':prepare,'evaluate':evaluate}[args.mode](args,client)
