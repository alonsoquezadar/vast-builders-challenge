"""Idempotently update only FireTrace's visual function, preserving gateway assets and secrets."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess


def function_span(source,name):
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return node.lineno-1,node.end_lineno


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--ssh-host',default='bc-alonsoayudantia2016')
    parser.add_argument('--namespace',default='team-23')
    args=parser.parse_args()
    if not re.fullmatch(r'team-\d+',args.namespace) or not re.fullmatch(r'[A-Za-z0-9_.-]+',args.ssh_host):parser.error('Invalid target')
    prefix=f'KUBECONFIG=/config/{args.namespace}-k8s.yaml kubectl -n {args.namespace}'
    def ssh(command,body=None):
        return subprocess.check_output(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',args.ssh_host,command],input=body)
    receipt=json.loads(ssh(prefix+' get configmap firetrace-code -o json'))
    old=receipt['data']['main.py'];newlines=old.splitlines(keepends=True)
    root=Path(__file__).parent
    local=(root/'main.py').read_text();lo,hi=function_span(local,'analyze')
    function=''.join(local.splitlines(keepends=True)[lo:hi])
    lo,hi=function_span(old,'analyze');newlines[lo:hi]=[function+'\n']
    updated=''.join(newlines)
    marker='# FireTrace structured visual gateway imports\n'
    if marker not in updated:
        updated=marker+"import base64, hashlib, json, os, re\nfrom datetime import datetime, timezone\nBACKEND_PROXY = ''\n"+updated
    ast.parse(updated)
    module=(root/'observation_schema.py').read_text()
    changed=updated!=old or receipt['data'].get('observation_schema.py')!=module
    print(json.dumps({'changed':changed,'oldSha256':hashlib.sha256(old.encode()).hexdigest(),'newSha256':hashlib.sha256(updated.encode()).hexdigest(),'apply':args.apply}))
    if not changed or not args.apply:return
    patch={'metadata':{'resourceVersion':receipt['metadata']['resourceVersion']},'data':{'main.py':updated,'observation_schema.py':module}}
    ssh(prefix+' patch configmap firetrace-code --type merge --patch-file /dev/stdin',json.dumps(patch).encode())
    ssh(prefix+' rollout restart deployment/firetrace')
    print(ssh(prefix+' rollout status deployment/firetrace --timeout=60s').decode().strip())

if __name__=='__main__':main()
