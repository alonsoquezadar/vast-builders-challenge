"""Deploy to the team's existing Kubernetes cluster without replacing other apps.

Run on the lab VM: python3 deploy.py --config /config/team-23.config
The default creates an isolated Deployment and Service, without changing Ingress.
"""
import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--vss-url', help='Cluster-reachable backend URL, when the VM URL does not resolve in pods.')
    args = parser.parse_args()
    config = {}
    for line in Path(args.config).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.removeprefix('export ').split('=', 1)
            parsed = shlex.split(value)
            config[key.strip()] = parsed[0] if parsed else ''
    ns = config['USERNAME']
    if not ns.startswith('team-') or not ns[5:].isdigit():
        raise ValueError('Invalid team namespace')
    env = {**os.environ, 'KUBECONFIG': f'/config/{ns}-k8s.yaml'}

    def apply(resource):
        result = subprocess.run(['kubectl', '-n', ns, 'apply', '-f', '-'], input=json.dumps(resource),
                                text=True, capture_output=True, env=env)
        if result.returncode:
            raise RuntimeError(f"Could not apply {resource['kind']}; kubectl exited {result.returncode}.")
        print(result.stdout.strip())

    name = 'firetrace'
    labels = {'app': name}
    meta = {'name': name, 'namespace': ns, 'labels': labels}
    code = {f: (Path(__file__).parent / f).read_text() for f in ['main.py', 'index.html', 'style.css', 'app.js', 'geo.mjs', 'demo_bundle.py']}
    apply({'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {**meta, 'name': name+'-code'}, 'data': code})
    secrets = {'VSS_URL': args.vss_url or config['INGRESS_URL'], 'VSS_USERNAME': ns, 'VSS_PASSWORD': config['PASSWORD'],
               'GPU_BEARER_TOKEN': config.get('GPU_BEARER_TOKEN', '')}
    apply({'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {**meta, 'name': name+'-credentials'},
           'type': 'Opaque', 'stringData': secrets})
    apply({'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': meta, 'spec': {
        'replicas': 1, 'selector': {'matchLabels': labels}, 'template': {'metadata': {'labels': labels}, 'spec': {
            'containers': [{'name': name, 'image': 'python:3.12-slim', 'command': ['python', 'main.py'],
                            'workingDir': '/code', 'ports': [{'containerPort': 8080}],
                            'envFrom': [{'secretRef': {'name': name+'-credentials'}}],
                            'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '1', 'memory': '512Mi'}},
                            'readinessProbe': {'httpGet': {'path': '/health', 'port': 8080}, 'initialDelaySeconds': 3},
                            'volumeMounts': [{'name': 'code', 'mountPath': '/code', 'readOnly': True}]}],
            'volumes': [{'name': 'code', 'configMap': {'name': name+'-code'}}]}}}})
    apply({'apiVersion': 'v1', 'kind': 'Service', 'metadata': meta, 'spec': {
        'selector': labels, 'ports': [{'port': 80, 'targetPort': 8080}]}})
    subprocess.run(['kubectl', '-n', ns, 'rollout', 'restart', 'deployment/firetrace'], env=env, check=True)
    subprocess.run(['kubectl', '-n', ns, 'rollout', 'status', 'deployment/firetrace', '--timeout=90s'], env=env, check=True)
    print('FireTrace service ready. Existing Ingress routes were preserved.')


if __name__ == '__main__':
    main()
