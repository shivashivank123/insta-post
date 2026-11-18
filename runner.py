"""Runs each channel's own post_next.py from its private repo, so the Actions minutes are spent here.

RUNNER_CONFIG (a secret) is a JSON list, one entry per channel:
    {"name": ..., "repo": "git@github.com:<owner>/<repo>.git", "deploy_key": ..., "ig_user_id": ..., "token_key": ...,
     "fb_page_id": ..., "fb_page_token": ...}   # fb_* optional: Facebook Page cross-post + old-reel backlog

For each channel: clone the repo with its deploy key, run `python3 post_next.py` (or `--refresh`) inside it, and
push the changed files back. With fb_* set, post mode also runs the repo's fb_backlog.py (one old reel to
Facebook per hour, if the repo has it). The repo's own script and post.yml decide when to post. This log is public, so it
only shows "channel N: <result>"; names, captions, links and errors stay out of it.

    python3 runner.py post      # post where a slot is free (FORCE=1 to skip the hour check, CHANNEL=N for one)
    python3 runner.py refresh   # renew every token into token.enc
"""
import json, os, subprocess, sys, tempfile

MODE = sys.argv[1] if len(sys.argv) > 1 else 'post'
FILES = {'post': ['queue.json', 'README.md', 'fb_backlog.json'], 'refresh': ['token.enc']}[MODE]


def mask(value):
    for line in str(value).splitlines():
        if line.strip():
            print(f'::add-mask::{line.strip()}')


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def result(out):
    if 'published' in out or 'token refreshed' in out:
        return 'done' if MODE == 'refresh' else 'posted'
    if 'failed:' in out:
        return 'post failed (see queue.json)'
    if 'queue empty' in out:
        return 'queue empty'
    return 'nothing to do'


def channel(n, ch, work):
    key = os.path.join(work, f'key{n}')
    with open(key, 'w') as f:
        f.write(ch['deploy_key'].strip() + '\n')
    os.chmod(key, 0o600)
    env = {**os.environ, 'GIT_SSH_COMMAND': f'ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'}
    repo = os.path.join(work, f'ch{n}')
    if run(['git', 'clone', '-q', ch['repo'], repo], env=env).returncode:
        return 'clone failed'
    script = ['python3', 'post_next.py'] + (['--refresh'] if MODE == 'refresh' else [])
    env = {**env, 'IG_USER_ID': ch['ig_user_id'], 'TOKEN_KEY': ch['token_key']}
    if ch.get('fb_page_id'):
        env.update(FB_PAGE_ID=ch['fb_page_id'], FB_PAGE_TOKEN=ch['fb_page_token'])
    p = run(script, cwd=repo, env=env)
    status = result(p.stdout) if p.returncode == 0 else 'script error'
    if MODE == 'post' and ch.get('fb_page_id') and os.path.exists(os.path.join(repo, 'fb_backlog.py')):
        b = run(['python3', 'fb_backlog.py'], cwd=repo, env=env)
        status += ', fb backlog ' + ('error' if b.returncode else 'posted' if '\nfacebook ' in '\n' + b.stdout
                                     else 'failed' if 'failed:' in b.stdout else 'nothing to do')
    run(['git', 'add'] + [f for f in FILES if os.path.exists(os.path.join(repo, f))], cwd=repo)
    if run(['git', 'diff', '--cached', '--quiet'], cwd=repo).returncode == 0:
        return status
    bot = f"{ch['name']}-autopost"
    msg = 'refresh token' if MODE == 'refresh' else 'posted from queue'
    run(['git', '-c', f'user.name={bot}', '-c', f'user.email={bot}@users.noreply.github.com',
         'commit', '-q', '-m', msg], cwd=repo)
    for _ in range(3):
        if run(['git', 'pull', '-q', '--rebase'], cwd=repo, env=env).returncode == 0 and \
                run(['git', 'push', '-q'], cwd=repo, env=env).returncode == 0:
            return status
    return status + ', push FAILED'


def main():
    channels = json.loads(os.environ['RUNNER_CONFIG'])
    for ch in channels:
        for k in ('name', 'repo', 'ig_user_id', 'token_key', 'deploy_key', 'fb_page_id', 'fb_page_token'):
            if ch.get(k):
                mask(ch[k])
    only = os.environ.get('CHANNEL')
    bad = False
    with tempfile.TemporaryDirectory() as work:
        for n, ch in enumerate(channels, 1):
            if only and str(n) != only:
                continue
            try:
                status = channel(n, ch, work)
            except Exception as e:
                status = f'runner error ({type(e).__name__})'
            bad |= 'error' in status or 'FAILED' in status or 'clone failed' in status
            print(f'channel {n}: {status}', flush=True)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
