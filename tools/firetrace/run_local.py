"""Start the local replay demo and a private SSH connection to the lab's Cosmos gateway."""
import argparse
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time


def port(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError('Port must be between 1 and 65535.')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=port, default=5173)
    parser.add_argument('--proxy-port', type=port, default=5175)
    parser.add_argument('--remote-port', type=port, default=18741)
    parser.add_argument('--ssh-host', default='bc-alonsoayudantia2016')
    parser.add_argument('--namespace', default='team-23')
    parser.add_argument('--saved-only', action='store_true', help='Use saved responses without connecting to the lab.')
    args = parser.parse_args()
    if not re.fullmatch(r'team-\d+', args.namespace) or not re.fullmatch(r'[A-Za-z0-9_.-]+', args.ssh_host):
        parser.error('Invalid namespace or SSH host.')
    processes = []
    env = {**os.environ, 'HOST': '127.0.0.1', 'PORT': str(args.port), 'FIRETRACE_REPLAY': 'demo-data.json'}
    try:
        if not args.saved_only:
            command = (f'KUBECONFIG=/config/{args.namespace}-k8s.yaml '
                       f'kubectl -n {args.namespace} port-forward --address 127.0.0.1 svc/firetrace {args.remote_port}:80')
            tunnel = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                                       '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
                                       '-o', 'ServerAliveCountMax=2', '-L',
                                       f'127.0.0.1:{args.proxy_port}:127.0.0.1:{args.remote_port}', args.ssh_host, command],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(tunnel)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and tunnel.poll() is None:
                try:
                    with socket.create_connection(('127.0.0.1', args.proxy_port), timeout=.3):
                        break
                except OSError:
                    time.sleep(.2)
            if tunnel.poll() is None:
                env['FIRETRACE_BACKEND_PROXY'] = f'http://127.0.0.1:{args.proxy_port}'
                print('Private laboratory connection started. Saved responses remain available if the connection fails.', flush=True)
            else:
                print('Could not connect to the laboratory. The map and saved responses remain available.', flush=True)
                env.pop('FIRETRACE_BACKEND_PROXY', None)
        else:
            env.pop('FIRETRACE_BACKEND_PROXY', None)
            env.pop('GPU_BEARER_TOKEN', None)
            env.pop('VSS_URL', None)
        server = subprocess.Popen([sys.executable, str(Path(__file__).with_name('main.py'))], env=env)
        processes.append(server)
        print(f'FireTrace local: http://localhost:{args.port}/', flush=True)
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == '__main__':
    main()
